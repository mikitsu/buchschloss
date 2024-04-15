"""general form definitions"""

from typing import Any, Optional, ClassVar
import enum

from .. import core
from .. import config
from .. import utils
from .lib import Widget as W, Form

NonEmptyEntry = (W.ENTRY, 'error', {'max_history': 0})
NonEmptyREntry = (W.ENTRY, 'error', {})
ClassEntry = (W.ENTRY, 'error', {'regex': config.gui2.class_regex})
IntEntry = (W.ENTRY, 'error', {'transform': int})
NullIntEntry = (W.ENTRY, 'none', {'transform': int})
NullEntry = (W.ENTRY, 'none', {'max_history': 0})
NullREntry = (W.ENTRY, 'none', {})
ScriptNameEntry = (W.ENTRY, 'error', {'regex': r'^[a-zA-Z0-9 _-]*$'})
PasswordEntry = (W.ENTRY, 'keep', {'extra_kwargs': {'show': '*'}})


class AForm(Form):
    """Use utils.get_name"""
    form_name: ClassVar[str]
    leaf_children: ClassVar[set] = set()

    def __init_subclass__(cls, **kwargs):
        """Set cls.form_name"""
        __class__.leaf_children -= {c for c in __class__.leaf_children if issubclass(cls, c)}
        __class__.leaf_children.add(cls)
        cls.form_name = cls.__name__.replace('Form', '')
        super().__init_subclass__(**kwargs)  # noqa -- it might accept kwargs later

    def get_name(self, name):
        """redirect to utils.get_name inserting a form-specific prefix"""
        if isinstance(self.tag, FormTag):
            items = ('form', self.form_name, self.tag.name, name)
        else:
            items = ('form', self.form_name, name)
        return utils.get_name('::'.join(items))


class FormTag(enum.Enum):
    SEARCH = '"search" action'
    NEW = '"new" action'
    EDIT = '"edit" action'
    VIEW = '"view" action'


class SearchForm(AForm):
    """Add search options (and/or) + exact matching and adapt widgets"""
    # PyCharm seems not to inherit the hint...
    all_widgets: 'dict[str, dict[Any, Optional[tuple]]]' = {
        'search_mode': {FormTag.SEARCH: (
            W.RADIO_CHOICES, [(c, utils.get_name(c)) for c in ('and', 'or')], {})},
        'exact_match': {FormTag.SEARCH: W.CHECKBOX},
    }

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for ws in cls.all_widgets.values():
            if ws[None] is not None:
                w, *a, kw = ws[None]
                if w in (W.CHECKBOX, W.OPTIONS_FROM_SEARCH):
                    kw = {**kw, 'allow_none': True}
                    ws.setdefault(FormTag.SEARCH, (w, *a, kw))
                elif w is W.DROPDOWN_CHOICES:
                    if a:
                        a = (((None, ''), *a[0]), *a[1:])
                    else:
                        kw['choices'] = ((None, ''), *kw['choices'])
                    ws.setdefault(FormTag.SEARCH, (w, *a, kw))


class AuthedForm(AForm):
    """add a 'current_password' field for NEW and EDIT"""
    all_widgets = {
        'current_password': {
            FormTag.NEW: PasswordEntry,
            FormTag.EDIT: PasswordEntry,
        }
    }


class EditForm(AForm):
    """Adapt forms for the EDIT action.

    On FormTag.EDIT:
    Use OptionsFromSearch with setter=True for the first not-inherited widget.
    Modify ``.get_data`` to include the value of the first widget under ``'*args'``.
    """
    id_name: ClassVar[str]

    def __init_subclass__(cls, **kwargs):
        if not cls.all_widgets:
            super().__init_subclass__(**kwargs)
            return
        cls.id_name = next(iter(cls.all_widgets))
        super().__init_subclass__(**kwargs)
        widget_spec = cls.all_widgets[cls.id_name]
        widget_spec.setdefault(FormTag.EDIT, (
            W.OPTIONS_FROM_SEARCH,
            getattr(core, cls.form_name),
            {'setter': True},
        ))


class ViewForm(AForm):
    """Adapt a form to be suitable with FormTag.VIEW

    Don't show a submit button when used with FormTag.VIEW.

    Insert display widgets (DisplayWidget or LinkWidget) on subclassing
    where a specific widget for FormTag.VIEW is not specified.
    The widget and arguments are chosen based on the default widget:

    - ``SearchMultiChoice`` creates a ``LinkWidget`` with ``multiple=True``
    - ``OptionsFromSearch`` creates a normal ``LinkWidget``
    - ``Checkbox`` creates a ``Checkbox`` with ``active=False``
    - ``MultiChoicePopup`` creates a ``DisplayWidget`` with ``display='list'``
    - everything else creates a ``DisplayWidget`` with ``display='str'``
    """
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for ws in cls.all_widgets.values():
            if ws[None] is None:
                continue
            w, *a, kw = ws[None]
            if w in (W.SEARCH_MULTI_CHOICE, W.OPTIONS_FROM_SEARCH):
                ans = a[0] if a else kw.pop('action_ns')
                new = (
                    W.LINK,
                    ans.__name__,
                    {'multiple': w is W.SEARCH_MULTI_CHOICE},
                )
            elif w is W.CHECKBOX:
                new = (W.CHECKBOX, {'active': False})
            else:
                display = 'list' if w is W.MULTI_CHOICE_POPUP else 'str'
                new = (W.DISPLAY, display, {})
            ws.setdefault(FormTag.VIEW, new)


class BookForm(SearchForm, EditForm, ViewForm):
    all_widgets = {
        'id': {
            FormTag.VIEW: W.DISPLAY,
            FormTag.SEARCH: None,
        },
        'isbn': {
            FormTag.NEW: (W.ISBN_ENTRY, True, {}),
            None: (W.ISBN_ENTRY, False, {}),
        },
        'author': NonEmptyREntry,
        'title': NonEmptyEntry,
        'series': W.SERIES_INPUT,
        'series_number': W.SERIES_INPUT_NUMBER,
        'language': NonEmptyREntry,
        'publisher': NonEmptyREntry,
        'concerned_people': NullREntry,
        'year': IntEntry,
        'medium': NonEmptyREntry,
        'borrow': {FormTag.VIEW: (
            W.LINK,
            'person',
            {'attr': 'person'},
        )},
        'genres': (W.MULTI_CHOICE_POPUP, core.Book.get_all_genres, {'new': True}),
        'library': (W.OPTIONS_FROM_SEARCH, core.Library, {'search': False}),
        'groups': (W.MULTI_CHOICE_POPUP, core.Book.get_all_groups, {'new': True}),
        'shelf': NonEmptyREntry,
    }


class PersonForm(SearchForm, EditForm, ViewForm):
    all_widgets = {
        'id': IntEntry,
        'first_name': NonEmptyREntry,
        'last_name': NonEmptyREntry,
        'class_': ClassEntry,
        'max_borrow': IntEntry,
        'borrows': {FormTag.VIEW: (
            W.LINK,
            'book',
            {'attr': 'book', 'multiple': True},
        )},
        'libraries': (W.SEARCH_MULTI_CHOICE, core.Library, {}),
        'pay': {
            FormTag.SEARCH: None,
            FormTag.VIEW: None,
            None: W.CHECKBOX,
        },
        'borrow_permission': {FormTag.VIEW: W.DISPLAY},
    }


class MemberForm(AuthedForm, SearchForm, EditForm, ViewForm):
    all_widgets = {
        'name': NonEmptyREntry,
        'level': (W.DROPDOWN_CHOICES, tuple(utils.level_names.items()), 1, {'search': False}),
        'password': {FormTag.NEW: W.CONFIRMED_PASSWORD_INPUT},
    }


class LibraryForm(SearchForm, EditForm, ViewForm):
    all_widgets = {
        'name': NonEmptyREntry,
        'pay_required': W.CHECKBOX,
    }


class BorrowForm(ViewForm):
    # NOTE: this form is actually only used for NEW and VIEW
    # EDIT is split into restitute + extend, SEARCH is separate
    all_widgets = {
        'person': (W.OPTIONS_FROM_SEARCH, core.Person, {}),
        'book': (W.OPTIONS_FROM_SEARCH, core.Book, {
            'condition': ('not', ('exists', ('borrow.is_back', 'eq', False)))}),
        'weeks': {FormTag.NEW: IntEntry},
        'override': {FormTag.NEW: W.CHECKBOX},
        'return_date': {FormTag.VIEW: W.DISPLAY},
    }


class BorrowRestituteForm(AForm):
    all_widgets = {
        'book': (W.OPTIONS_FROM_SEARCH, core.Book,
                 {'condition': ('borrow.is_back', 'eq', False)}),
    }


class BorrowExtendForm(AForm):
    all_widgets = {
        'book': (W.OPTIONS_FROM_SEARCH, core.Book,
                 {'condition': ('borrow.is_back', 'eq', False)}),
        'weeks': IntEntry,
    }


class BorrowSearchForm(SearchForm):
    all_widgets = {
        'book__title': NullREntry,
        'book__author': NullREntry,
        'book__library': (W.OPTIONS_FROM_SEARCH, core.Library, {}),
        'book__groups': (W.MULTI_CHOICE_POPUP, core.Book.get_all_groups, {}),
        # this has on_empty='error', but empty values are removed when searching
        # the Null*Entries above are not really needed
        'person__class_': ClassEntry,
        'person__libraries': (W.SEARCH_MULTI_CHOICE, core.Library, {}),
        'is_back': (W.CHECKBOX, {'allow_none': True}),
    }


class ScriptForm(AuthedForm, SearchForm, EditForm, ViewForm):
    all_widgets = {
        'name': ScriptNameEntry,
        'permissions': {
            None: (W.MULTI_CHOICE_POPUP, [
                (p.name, utils.get_name('script::permissions::' + p.name))
                for p in core.ScriptPermissions], {}),
            FormTag.VIEW: (W.DISPLAY, 'list', {'get_name': 'script::permissions::'}),
        },
        'setlevel': (W.DROPDOWN_CHOICES,
                     ((None, '-----'), *utils.level_names.items()), {}),
        'code': {
            None: W.TEXT,
            FormTag.SEARCH: None,
            FormTag.VIEW: None,
        }
    }
