"""Abstract (UI-agnostic) form definitions"""

from typing import ClassVar, Any, Optional
import enum


class Widget(enum.Enum):
    """Enum for widget (field) types"""
    ENTRY = 'Entry'
    RADIO_CHOICES = 'RadioChoices'
    DROPDOWN_CHOICES = 'DropdownChoices'
    MULTI_CHOICE_POPUP = 'MultiChoicePopup'
    OPTIONS_FROM_SEARCH = 'OptionsFromSearch'
    FALLBACK_OFS = 'FallbackOFS'
    SERIES_INPUT = 'SeriesInput'
    SERIES_INPUT_NUMBER = 'SeriesInputNumber'
    CONFIRMED_PASSWORD_INPUT = 'ConfirmedPasswordInput'
    ISBN_ENTRY = 'ISBNEntry'
    TEXT = 'Text'
    CHECKBOX = 'Checkbox'
    SEARCH_MULTI_CHOICE = 'SearchMultiChoice'
    DISPLAY = 'DisplayWidget'
    LINK = 'LinkWidget'


class Form:
    """Represent a family of forms

    Families are specified by subclassing and setting the ``all_widgets`` attribute.
    It is merged with the superclasses' attributes.
    To remove a specification by a superclass, explicitly set it to ``None``.
    The ``all_widgets`` attribute is a dict of the form::

        {
            field: {
                tag: widget_spec,
                tag_2: widget_spec_2,
                ...,
                None: default_widget_spec,
            },
            field_2: tag_dict_2,  # may also be a widget spec
            ...
            field_n: tag_dict_n,  # may also be a widget spec
        }

    Where ``field`` is a field name (passed to widgets and used as default result key),
    ``tag`` is a form tag (see below) with ``None`` indicating the default
    and a ``widget_spec`` specifies a ``Widget`` either as an enum element, in which
    case the instance will be created without arguments or as a ``(elem, *args, kwargs)``
    tuple, in which case the instance will be created with ``*args`` and  ``**kwargs``.
    It may also be ``None``, in which case no widget is created.

    When instantiating a form, a tag value is given.
    It should be a string or an enum value, although every hashable object should work.
    This tag is available as ``.tag`` (for use in e.g. validation functions)
    and is used to choose the appropriate widget for a field.

    To actually use the forms, yuo need to override the ``make_widget`` method
    specifying how widget instances are actually contructed.
    """

    # note: this type hint is the post-processing type
    all_widgets: ClassVar[dict[str, dict[Any, Optional[tuple]]]] = {}
    widget_dict: dict[str, Any]

    def __init_subclass__(cls):
        """Merge the new and old ``all_widgets`` handling convenience shorthands"""
        # first, handle convenience shorthands
        for field, tag_spec in cls.all_widgets.items():
            if not isinstance(tag_spec, dict):
                tag_spec = {None: tag_spec}
            cls.all_widgets[field] = {
                tag: ws if isinstance(ws, (tuple, type(None))) else (ws, {})
                for tag, ws in tag_spec.items()
            }
            cls.all_widgets[field].setdefault(None, None)
        # second, merge
        all_widgets = {}
        for superclass in reversed(cls.__mro__):  # is there a way to get direct parents?
            if not issubclass(superclass, Form):
                continue
            for field, tag_spec in superclass.all_widgets.items():
                all_widgets.setdefault(field, {}).update(tag_spec)
        cls.all_widgets = all_widgets

    def __init__(self, tag):
        """Create a tag-specific form selecting the appropriate widgets"""
        self.tag = tag
        self.widget_dict = {}
        for name, w_options in self.all_widgets.items():
            widget = w_options.get(tag, w_options[None])
            if widget is not None:
                w_elem, *w_args, w_kwargs = widget
                self.widget_dict[name] = self.make_widget(name, w_elem, w_args, w_kwargs)

    def make_widget(self, name, w_elem, w_args, w_kwargs):
        """Override this method to actually create widgets"""
        raise NotImplementedError
