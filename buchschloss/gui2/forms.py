"""forms"""
import enum

from . import formlib

from .. import config
from .. import core
from .. import utils

from .formlib import RadioChoices, DropdownChoices
from .widgets import (ISBNEntry, NonEmptyEntry, NonEmptyREntry, ClassEntry, PasswordEntry,
                      IntEntry, NullREntry, Text, ConfirmedPasswordInput,
                      Checkbox, SeriesInput, OptionsFromSearch, search_multi_choice,
                      FlagEnumMultiChoice, ScriptNameEntry, MultiChoicePopup)


class FormTag(enum.Enum):
    SEARCH = '"search" action'
    NEW = '"new" action'
    EDIT = '"edit" action'


class BaseForm(formlib.Form):
    """Base class for forms, handling get_name, default content and autocompletes"""
    form_name: str

    def __init__(self, frame, tag, submit_callback):
        super().__init__(frame, tag, submit_callback)
        self.set_data(config.gui2.entry_defaults.get(self.form_name).mapping)

    def __init_subclass__(cls, **kwargs):
        """Handle autocompletes and set cls.form_name"""
        cls.form_name = cls.__name__.replace('Form', '')
        # This will put every widget spec into the standard form, required below
        super().__init_subclass__(**kwargs)  # noqa -- it might accept kwargs later

        for k, v in config.gui2.get('autocomplete').get(cls.form_name).mapping.items():
            if k in cls.all_widgets:
                for *_, w_kwargs in cls.all_widgets[k].values():
                    w_kwargs.setdefault('autocomplete', v)

    def get_name(self, name):
        """redirect to utils.get_name inserting a form-specific prefix"""
        return utils.get_name('::'.join(('form', self.form_name, name)))


class SearchForm(BaseForm):
    """Add search options (and/or) + exact matching"""
    all_widgets = {
        'search_mode': {FormTag.SEARCH: (
            RadioChoices, [(c, utils.get_name(c)) for c in ('and', 'or')], {})},
        'exact_match': {FormTag.SEARCH: Checkbox},
    }

    def get_data(self):
        """ignore empty data"""
        if self.tag is FormTag.SEARCH:
            return {k: v for k, v in super().get_data() if v or isinstance(v, bool)}
        else:
            return super().get_data()

    def validate(self):
        """ignore errors from empty widgets"""
        errors = super().validate()
        # NOTE: the password entry will raise ValueError if the passwords don't
        # match, but it shouldn't be used in searches anyway.
        # All other widgets shouldn't raise exceptions in .get()
        if self.tag is FormTag.SEARCH:
            data = self.get_data()
            for k in errors.keys() - data.keys():
                del errors[k]


class AuthedForm(BaseForm):
    """add a 'current_password' field"""
    all_widgets = {
        'current_password': {
            FormTag.SEARCH: None,
            None: PasswordEntry,
        }
    }


class SetForEditForm(BaseForm):
    """Use OptionsFromSearch with setter=True for the first widget on FormTag.EDIT"""
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        widget_spec = next(iter(cls.all_widgets.values()))
        if FormTag.EDIT in widget_spec:
            raise TypeError("can't use SetForEditForm if FormTag.EDIT is specified")
        widget_spec[FormTag.EDIT] = (OptionsFromSearch, getattr(core, cls.form_name), {})


class BookForm(SearchForm, SetForEditForm):
    all_widgets = {
        'id': {},
        'isbn': ISBNEntry,
        'author': NonEmptyREntry,
        'title': NonEmptyEntry,
        'series': SeriesInput,
        'language': NonEmptyREntry,
        'publisher': NonEmptyREntry,
        'concerned_people': NullREntry,
        'year': IntEntry,
        'medium': NonEmptyREntry,
        'genres': (MultiChoicePopup, lambda: core.Book.get_all_genres(), {}),
        'library': {
            None: (OptionsFromSearch, core.Library, {}),
            FormTag.SEARCH: (OptionsFromSearch, core.Library, {'allow_none': True}),
        },
        'groups': (MultiChoicePopup, lambda: core.Book.get_all_groups(), {}),
        'shelf': NonEmptyREntry,
    }


class PersonForm(SearchForm, SetForEditForm):
    all_widgets = {
        'id_': {
            FormTag.SEARCH: None,
            FormTag.NEW: IntEntry,
        },
        'first_name': NonEmptyREntry,
        'last_name': NonEmptyREntry,
        'class_': ClassEntry,
        'max_borrow': IntEntry,
        'libraries': search_multi_choice(core.Library),
        'pay': {
            FormTag.SEARCH: None,
            None: Checkbox,
        },
    }


class MemberForm(AuthedForm, SearchForm, SetForEditForm):
    all_widgets = {
        'name': NonEmptyREntry,
        'level': (formlib.DropdownChoices, tuple(utils.level_names.items()), 1, {}),
        'password': {FormTag.NEW: ConfirmedPasswordInput},
    }


class MemberChangePasswordForm(AuthedForm):
    all_widgets = {
        'member': NonEmptyREntry,
        'new_password': ConfirmedPasswordInput,
    }


class LoginForm(BaseForm):
    all_widgets = {
        'name': NonEmptyREntry,
        'password': PasswordEntry,
    }


class LibraryForm(SearchForm, SetForEditForm):
    all_widgets = {
        'name': NonEmptyREntry,
        'books': {FormTag.SEARCH: None,
                  None: search_multi_choice(core.Book)},
        'people': {FormTag.SEARCH: None,
                   None: search_multi_choice(core.Person)},
        'pay_required': Checkbox,
        'action': {
            FormTag.EDIT: (
                DropdownChoices,
                [(e, utils.get_name('from::library::action::' + e.value))
                 for e in core.LibraryAction],
                {},
            ),
        },
    }


class BorrowForm(BaseForm):
    all_widgets = {
        'person': (OptionsFromSearch, core.Person, {}),
        'book': (OptionsFromSearch, core.Book, {}),
        'weeks': IntEntry,
        'override': Checkbox,
    }


class BorrowRestituteForm(BaseForm):
    all_widgets = {
        'book': (OptionsFromSearch, core.Book,
                 {'condition': ('borrow.is_back', 'eq', False)}),
    }


class BorrowExtendForm(BaseForm):
    all_widgets = {
        'book': (OptionsFromSearch, core.Book, {}),
        'weeks': IntEntry,
    }


class BorrowSearchForm(SearchForm):
    all_widgets = {
        'book__title': NullREntry,
        'book__author': NullREntry,
        'book__library': (OptionsFromSearch, core.Library, {'allow_none': True}),
        'book__groups': (MultiChoicePopup, lambda: core.Book.get_all_groups(), {}),
        # this has on_empty='error', but empty values are removed when searching
        # the Null*Entries above are not really needed
        'person__class_': ClassEntry,
        'person__libraries': search_multi_choice(core.Library),
        'is_back': (Checkbox, {'allow_none': True}),
    }


class ScriptForm(AuthedForm, SearchForm, SetForEditForm):
    all_widgets = {
        'name': ScriptNameEntry,
        'permissions': (FlagEnumMultiChoice, core.ScriptPermissions, {}),
        'setlevel': (formlib.DropdownChoices,
                     ((None, '-----'), *utils.level_names.items()), {}),
        'code': {
            None: Text,
            FormTag.SEARCH: None,
        }
    }
