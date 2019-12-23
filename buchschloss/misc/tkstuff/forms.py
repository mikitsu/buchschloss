"""Django-like (in the sense of "class-based") forms for tkinter"""

import inspect
import copy
import tkinter as tk
import tkinter.messagebox as tk_msg
import misc.tkstuff as mtk

try:
    import typing
except ImportError:
    typing = None
import enum
import collections


class FormWidget(mtk.ContainingWidget):
    """Provide a subclass of ContainingWidget for forms

        Provide a way to validate contents and automaically display errors

        The widgets are expected to have a .validate() method returning
            a tuple consisting of a boolean indicating the validity of the data
            and the data itself or an error message,
            such as the one provided by misc.Validator
        Alternatively, the widgets may provide a .get() method returning the data.
        Additional validation (e.g. checking if entries match)
            can be done by overriding the .clean_data() method

        To validate the data, call the .validate() method.
            This will use the .clean_data() method for getting data
            and display any errors in the way specified in __init__
            It returns a boolean indicating if all data is valid
        After .validate() returned True, the data is available under.data

        By default, the submit action calls onsubmit (passed as argument)
            with the data if validation succeeds"""
    class ErrorHandle(enum.Flag):
        """Flags for how to display errors to the user

            LABEL: attach a Label to the widget
            POPUP: show a messagebox with the errors
            CUSTOM: call the .custom_error_handle() method

            The flags may be combined, execution order is not guaranteed"""
        LABEL = enum.auto()
        POPUP = enum.auto()
        CUSTOM = enum.auto()

    class SubmitOnReturn(enum.Enum):
        """Information regarding submit bindings on <Return> for elements

            NONE: do not bind
            LAST: bind to the last form element
            ALL: bind to all form elements
        """
        NONE = enum.auto()
        LAST = enum.auto()
        ALL = enum.auto()

    def __init__(self, master, *widgets,
                 error_handle=ErrorHandle.LABEL | ErrorHandle.POPUP,
                 error_display_options={},
                 submit_button=True,
                 onsubmit=lambda data: None,
                 default_content={},
                 take_focus=False,
                 submit_on_return=SubmitOnReturn.NONE,
                 **container_options):
        """Create a form.

            `widgets` are (<key>, (<class>, <kwargs>)) of the contained widgets
                The key is used in self.widget_dict, self.data and self.errors
                Note the default implementation of self.clean_data() ignores
                widgets whose keys start with ignore
            `error_handle` is a flag from FormWidget.ErrorHandle.
                See its __doc__ for details
            `error_display_options` are options for error display
                the following keys will be used:
                'label_font' the font used for error messages on labels
                'label_fg' the foreground color for labels, default red
                'label_position' the position of the label relative to the widget
                'popup_title' the title for the popup
                'popup_intro' the introducing text on the popup
                'popup_field_name_resolver' callable to get the display name for a particular field
            `submit_button` may be a dictionary containing options for an
                automatically generated one, any other truthy value to
                automatically generate a default one and a falsey value to
                suppress automatic generation of a button.
            `onsubmit` is a callable taking the forms data if the submit_action
                is triggered and self.validate() returned True.
                If finer-grained control over the process is wished,
                overriding `.submit_action` may be more appropriate.
            `default_content` is a mapping from field names to
                their default content for this form. The fields must
                have a setting method recognized by misc.tkstuff.get_setter.
            `take_focus` specifies if the first form element should take focus
            `submit_on_return` is an element of FormWIdget.SubmitOnReturn.
                see its __doc__ for destails
            `container_options` are passed along to ContainingWidget

            By default, the direction for the ContainingWidget is set to `tk.BOTTOM`

            See ContainingWidget.__init__ for more detais"""
        self.ERROR_LABEL_ID = object()
        self.error_handle = error_handle
        self.onsubmit = onsubmit
        self.error_display_options = {'label_fg': 'red',
                                      'label_position': tk.RIGHT}
        self.error_display_options.update(error_display_options)

        widget_keys = []
        pass_widgets = []
        for key, widget in widgets:
            if self.ErrorHandle.LABEL & error_handle:
                widget = (mtk.LabeledWidget,
                          {'widget': widget,
                           'text': '',
                           'position': self.error_display_options['label_position'],
                           'label_id': self.ERROR_LABEL_ID})
            widget_keys.append(key)
            pass_widgets.append(widget)

        if submit_button:
            sb_options = {'text': 'Submit', 'command': self.submit_action}
            if isinstance(submit_button, dict):
                sb_options.update(submit_button)
            pass_widgets.append((tk.Button, sb_options))
        options = {'direction': (tk.BOTTOM, tk.RIGHT)}
        options.update(container_options)

        super().__init__(master, *pass_widgets, **options)
        self.widget_dict = {k: w for k, w in zip(widget_keys, self.widgets)}

        for k, v in default_content.items():
            mtk.get_setter(self.widget_dict[k])(v)
        if submit_on_return is FormWidget.SubmitOnReturn.LAST:
            self.widgets[-1].bind('<Return>', self.submit_action)
        elif submit_on_return is FormWidget.SubmitOnReturn.ALL:
            for w in self.widgets:
                w.bind('<Return>', self.submit_action)
        if take_focus:
            self.widgets[0].focus()

    def validate(self):
        """Validate the form data and, if applicable,
            display errors according to self.error_handle

            Return a boolean indicating the validity of the entered data
            After the call, the processsed data is availabe under self.data"""
        self.data = {}
        self.errors = collections.defaultdict(set)
        self.clean_data()
        if self.ErrorHandle.LABEL & self.error_handle:
            options = {'fg': self.error_display_options['label_fg']}
            if self.error_display_options.get('label_font'):
                options['font'] = self.error_display_options['label_font']
            for k, w in self.widget_dict.items():
                w.labels[self.ERROR_LABEL_ID].config(
                    text='\n'.join(self.errors[k]), **options)
        if self.ErrorHandle.POPUP & self.error_handle:
            text = [self.error_display_options.get('popup_intro', '')]
            for k, v in self.errors.items():
                if v:
                    text.append('{}: {}'.format(
                        self.error_display_options.get('popup_field_name_resolver',
                                                       lambda txt: txt)(k),
                        '\n'.join(v)))
            if len(text) > 1:
                tk_msg.showerror(self.error_display_options.get('popup_title'),
                                 '\n\n'.join(text))
        if self.ErrorHandle.CUSTOM & self.error_handle:
            self.custom_error_handle()
        return not any(e for e in self.errors.values())

    def clean_data(self):
        """Use the .validate() methods of elements to validate form data.
            Override to validate in a finer-grained way

            Ignore elements whose keys start with 'ignore'"""
        for k, w in self.widget_dict.items():
            if k.startswith('ignore'):
                continue
            try:
                validator = w.validate
            except AttributeError:
                def validator(): return True, w.get()
            valid, data = validator()
            if valid:
                self.data[k] = data
            else:
                self.data[k] = None
                self.errors[k].add(data)

    def custom_error_handle(self):
        pass

    def submit_action(self, event=None):
        if self.validate():
            self.onsubmit(self.data)


class ProtoWidget(tuple):
    DEFAULT_DATA = {'groups': (), 'opt': 'out'}

    def __new__(cls, iterable=(), options={}):
        self = super().__new__(cls, iterable)

        data = cls.DEFAULT_DATA.copy()
        data.update(options)
        data['groups'] = set(data['groups'])
        for k, v in data.items():
            setattr(self, k, v)
        return self

    def use(self, widgets, groups):
        return bool(self[0] in widgets or self.groups & groups
                    ) ^ (self.opt == 'out')


class Form:
    """Factory for FormWidget.

        May be created by subclassing.
        See __init_subclass__ for more information

        The FormWidget is created by calling the subclass passing the master widget

        Templates are supported. They are created by passing `template=True`
        to the class creation. A template may contain elements
        and helper methods like any other form, but cannot be used as a
        factory. It can be used as a superclass for more secialised forms.
        In this case, it is not neccessary fot the form to explicitly
        inherit from `Form`.
        By default, the elements of a template are positioned after
        the elements of the using form. To override this, place the
        assignment `_position_over_ = True` in the template body.
        If templates are used for other templates, the `template=True`
        argument must be passed for each class definition.
    """

    def __new__(cls, master, elements=(), groups=(), **options):
        """Create a new form.

            `options` override the options defined in the form class
            `elements` is a container of widget keys to opt in/out*
            `groups` is an iterable of widget groups to opt in/out*

            * depending on setting in element definition
        """
        groups = set(groups)
        kwargs = cls.__formwidget_options.copy()
        kwargs.update(options)
        widgets = [copy.deepcopy(w) for w in cls.__widgets if w.use(elements, groups)]
        return cls.__form_class(master, *widgets, **kwargs)

    def __init_subclass__(cls, autogen_names=True, template=False):
        """Prepare a new form.

            elements are marked by Element (as annotation or type)
            Store the elements internally for use.

            If the `template` argument is true, only store the widgets for the
                given form elements. They will be used as soon as a
                non-template subclass is created. See Form.__doc__

            options for the FormWidget may be stored in a FormWidget nested class
                this applies to initialisation options and method overriding
                all data is available in the methods
                Note: the ** keyword arguments should be stored
                    in a mapping with the corresponding name, not separately

            the FormWidget nested class is used as class for the widget;
                inheritance is added if not already present.

            An element is a class and will be initialised with its master
                widget. To add custom arguments (such as colors or fonts),
                create a subclass and add your customisations in __init__

            If an element does not have a .validate() method, it is converted
                to a ValidatedWidget with an empty validator. This only
                work if it has a .get() or a .curselection() method

            If `autogen_names` (argument) is True (default),
                the elements are created as LabeledWidget instances.
                The user-facing name is chosen by the `get_name()` method,
                if it is not present, the variable name is used.
                if present, the `get_name` method is also used as
                error_display_options['popup_field_name_resolver'] argument

            Example:

            >>> from misc.tk import forms
            >>> import misc.tk as mtk
            >>> import tkinter as tk
            >>> from functools import partial

            >>> class MyRegisterForm(forms.Form):
            ...     class FormWidget:  # no need to explicitly inherit
            ...         error_handle = forms.FormWidget.ErrorHandle.LABEL
            ...
            ...         def clean_data(self):
            ...             super().clean_data()
            ...             if not self.check_username():
            ...                 self.errors['username'].add(
            ...                     'Username already taken')
            ...             if msg := self.check_email():
            ...                 self.errors['email'].add(msg)
            ...
            ...         def onsubmit(data):  # NOT self, it's used as argument
            ...             print('hey, look at this', data)
            ...             # do stuff
            ...
            ...         def check_username(self):  # these are just convenience methods
            ...             # lots of stuff here
            ...         def check_email(self):
            ...             # lots of stuff here
            ...
            ...     def email_validator(email):  # we can define temporary methods...
            ...         if email.count('@') == 1:
            ...             return True, email
            ...         else:
            ...             return False, 'not valid'
            ...     # ... and variables
            ...     ValidatedEntry = partial(mtk.ValidatedWidget.new_cls, tk.Entry)
            ...
            ...     username = forms.Element(tk.Entry)  # instead of annotations, this is OK
            ...     email: forms.Element = ValidatedEntry(email_validator)
            ...     password: forms.Element = ValidatedEntry(
            ...         lambda p: (True, p) if len(p) > 5
            ...                   else (False, 'Length must be at least 6'))
        """
        cls.__widgets = cls.__get_widgets(autogen_names)
        cls.__set_formwidget_prefs()
        if autogen_names and hasattr(cls, 'get_name'):
            cls.__formwidget_options.setdefault('error_display_options', {})[
                'popup_field_name_resolver'] = cls.get_name
        if not template:
            widgets = []
            for cls_in_mro in cls.__mro__:
                if cls_in_mro is Form:
                    break
                new_widgets = cls_in_mro.__widgets
                if getattr(cls_in_mro, '_position_over_', False):
                    widgets = new_widgets + widgets
                else:
                    widgets.extend(new_widgets)
            cls.__widgets = widgets

    @classmethod
    def __get_widgets(cls, autogen_names):
        def _get_element_data(name, thing):
            if issubclass(type_hints.get(name, type(None)), Element):
                return getattr(type_hints[name], 'data', {})
            else:
                try:
                    return thing._misc_tk_form_element_data
                except AttributeError:
                    return None

        type_hints = getattr(typing, 'get_type_hints', lambda c: {})(cls)
        widgets = []
        name_getter = getattr(cls, 'get_name', lambda x: x)
        for name, value in cls.__dict__.items():
            data = _get_element_data(name, value)
            if data is None:
                continue
            if isinstance(value, tuple):
                value, options = value
            else:
                options = {}
            if not hasattr(value, 'validate'):
                value = mtk.ValidatedWidget.new_cls(value, lambda x: (True, x))
            widget = (value, options)
            if autogen_names:
                widget = (mtk.LabeledWidget, {
                    'widget': widget,
                    'text': name_getter(name),
                    'label_id': '{}-{}-label'.format(cls, value)})
            widgets.append(ProtoWidget((name, widget), data))
        return widgets

    @classmethod
    def __set_formwidget_prefs(cls):
        form_widget = vars(cls).get('FormWidget')
        if form_widget:
            argspec = inspect.getfullargspec(FormWidget.__init__)
            # if we subclass a template, don't overwrite unless explicitly
            cls.__formwidget_options = getattr(
                cls, '_Form__formwidget_options', {}).copy()
            for k in argspec.kwonlyargs:
                try:
                    cls.__formwidget_options[k] = getattr(form_widget, k)
                except AttributeError:
                    pass
            cls.__formwidget_options.update(
                getattr(FormWidget, argspec.varkw, {}))
            bases = (form_widget, getattr(cls, '_Form__form_class', FormWidget))
            cls.__form_class = type(form_widget.__name__, bases, {})
        elif not hasattr(cls, '_Form__form_class'):
            cls.__form_class = FormWidget
            cls.__formwidget_options = {}


class Element:
    """A form element. Use as an annotation or as type (will create a subclass)"""
    def __new__(cls, thing=None, **options):
        """Mark as form element. May include options used by Form

            currently the only option:
            `groups` is a container of the groups the element belongs to.
                see Form.__new__ fro information on how to use them
        """
        if thing is None:
            return type('ElementWithOptions', (cls,), {'data': options})
        elif isinstance(thing, type):
            return type(thing.__name__ + 'FormElement',
                        (thing,),
                        {'_misc_tk_form_element_data': options})
        else:
            raise TypeError('To use with widget classes')
