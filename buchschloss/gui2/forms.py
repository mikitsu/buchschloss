"""forms"""
import functools
import enum

from . import formlib

from .. import config
from .. import core
from .. import utils

from .widgets import (ISBNEntry, NonEmptyEntry, NonEmptyREntry, ClassEntry, PasswordEntry,
                      IntEntry, NullREntry, Text, ConfirmedPasswordInput, Entry,
                      Checkbox, SeriesInput, OptionsFromSearch, SearchMultiChoice,
                      FlagEnumMultiChoice, ScriptNameEntry, MultiChoicePopup)


class FormTag(enum.Enum):
    SEARCH = '"search" action'
    NEW = '"new" action'
    EDIT = '"edit" action'


class BaseForm(formlib.Form):
    """Base class for forms, handling get_name, default content and autocompletes"""
    def __init_subclass__(cls, **kwargs):
        """Handle default content and autocompletes"""
        cls.form_name = cls.__name__.replace('Form', '')
        # This will put every widget spec into the standard form, required below
        super().__init_subclass__(**kwargs)  # noqa -- it might accept kwargs later

        for k, v in config.gui2.get('autocomplete').get(cls.form_name).mapping.items():
            if k in cls.all_widgets:
                for *_, w_kwargs in cls.all_widgets[k].values():
                    w_kwargs.setdefault('autocomplete', v)

        @functools.wraps(cls.__init__)
        def wrap__init__(self, *args, __wraps=cls.__init__, **kwargs):
            """wrap __init__ to insert default content"""
            __wraps(self, *args, **kwargs)
            self.set_data(config.gui2.entry_defaults.get(cls.form_name).mapping)
        cls.__init__ = wrap__init__

    def get_name(self, name):
        """redirect to utils.get_name inserting a form-specific prefix"""
        return utils.get_name('::'.join(('form', self.form_name, name)))


class SearchForm(BaseForm):
    """Add search options (and/or) + exact matching"""
    all_widgets = {
        # TODO: appropriate widget
        # 'search_mode':
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


class BookForm(SearchForm):
    all_widgets = {
        'id': {FormTag.EDIT: IntEntry},
        'isbn': ISBNEntry,
        'author': NonEmptyREntry,
        'title': NonEmptyEntry,
        'series': SeriesInput,
        'language': NonEmptyREntry,
        'publisher': NonEmptyREntry,
        'concerned_people': NullREntry,
        'year': IntEntry,
        'medium': NonEmptyREntry,
        # TODO: widget
        # 'genres': (OptionsFromSearch, core.Book, {})
        'library': {
            None: (OptionsFromSearch, core.Library, {}),
            FormTag.SEARCH: (OptionsFromSearch, core.Library, {'allow_none': True}),
        },
        # TODO: widget
        'groups': (OptionsFromSearch, core.Group, {}),
        'shelf': NonEmptyREntry,
    }

    # if config.gui2.genres.options is None:
    #     genres: mtkf.Element = (NullREntry, {'rem_key': 'book-genres'})
    # else:
    #     genres: mtkf.Element = (
    #         type('StrMultiChoicePopup', (MultiChoicePopup,),
    #              {'get': lambda s: s.sep.join(MultiChoicePopup.get(s))}),
    #         {'options': config.gui2.genres.options,
    #          'sep': config.gui2.genres.sep}
    #     )


class PersonForm(SearchForm):
    all_widgets = {
        'id_': {
            FormTag.SEARCH: None,
            None: IntEntry,
        },
        'first_name': NonEmptyREntry,
        'last_name': NonEmptyREntry,
        'class_': ClassEntry,
        'max_borrow': IntEntry,
        # TODO: widget
        # 'libraries': (SearchMultiChoice, core.Library, {}),
        'pay': {
            FormTag.SEARCH: None,
            None: Checkbox,
        },
    }


class MemberForm(AuthedForm, SearchForm):
    all_widgets = {
        'name': NonEmptyREntry,
        # TODO: OptionChoiceWidget
        # 'level':
        'password': {FormTag.NEW: ConfirmedPasswordInput},
    }
    # level: mtkf.Element = (mtk.OptionChoiceWidget,
    #                        {'values': list(utils.level_names.items()),
    #                         'default': 1})


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


# class LibraryGroupCommon(SearchForm, template=True):
#     _position_over_ = True
#     name: mtkf.Element = NonEmptyEntry
#     books: GroupElement.NO_SEARCH = (SearchMultiChoice, {'action_ns': core.Book})
#     # not as element to allow Library to have a nice order
#     action = (mtk.RadioChoiceWidget, {
#         '*args': [(a, get_name('form::LibraryGroupCommon::' + a))
#                   for a in ['add', 'remove', 'delete']]})
#
#
# class GroupForm(LibraryGroupCommon):
#     action: GroupElement.ONLY_EDIT = LibraryGroupCommon.action
#
#
# class LibraryForm(LibraryGroupCommon):
#     class FormWidget:
#         default_content = {'pay_required': True}
#
#     people: GroupElement.NO_SEARCH = (SearchMultiChoice, {'action_ns': core.Person})
#     pay_required: GroupElement.ONLY_NEW = CheckbuttonWithVar
#     action: GroupElement.ONLY_EDIT = LibraryGroupCommon.action
#
#
# class GroupActivateForm(BaseForm):
#     group: mtkf.Element = (OptionsFromSearch, {'action_ns': core.Group})
#     src: mtkf.Element = (SearchMultiChoice, {'action_ns': core.Library})
#     dest: mtkf.Element = (OptionsFromSearch, {'action_ns': core.Library})


class BorrowForm(BaseForm):
    all_widgets = {
        'person': (OptionsFromSearch, core.Person, {}),
        'book': (OptionsFromSearch, core.Book, {}),
        'weeks': IntEntry,
        'override': Checkbox,
    }


class BorrowRestituteForm(BaseForm):  # TODO: add a condition to OFS (wait for #69)
    all_widgets = {
        'book': (OptionsFromSearch, core.Book, {}),
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
        # TODO: widget
        # 'book__groups':
        # this has on_empty='error', but empty values are removed when searching
        # the Null*Entries above are not really needed
        'person__class_': ClassEntry,
        # TODO: widget
        # 'person__libraries':
        'is_back': (Checkbox, {'allow_none': True}),
    }
    # book__groups: mtkf.Element = (SearchMultiChoice, {'action_ns': core.Group})
    # person__libraries: mtkf.Element = (SearchMultiChoice, {'action_ns': core.Library})


class ScriptForm(AuthedForm, SearchForm):
    all_widgets = {
        'name': ScriptNameEntry,
        # TODO: widget
        # 'permissions':
        # 'setlevel':
        'code': {
            None: Text,
            FormTag.SEARCH: None,
        }
    }
    # permissions: mtkf.Element = (
    #     FlagEnumMultiChoice,
    #     {'flag_enum': core.ScriptPermissions, 'get_name_prefix': 'Script::permissions::'}
    # )
    # setlevel: mtkf.Element = (
    #     mtk.OptionChoiceWidget,
    #     {'values': ((None, '-----'), *utils.level_names.items())})
