"""forms"""

import tkinter as tk
import enum

from ..misc import tkstuff as mtk
from ..misc.tkstuff import forms as mtkf

from .. import config
from .. import core
from .. import utils
from ..utils import get_name

from .widgets import (ISBNEntry, NonEmptyEntry, NonEmptyREntry, ClassEntry,
                      IntEntry, NullREntry, Text,
                      IntListEntry, NonEmptyPasswordEntry, Entry,
                      OptionalCheckbuttonWithVar, CheckbuttonWithVar,
                      SeriesEntry, OptionsFromSearch, SearchMultiChoice,
                      FlagEnumMultiChoice, ScriptNameEntry, MultiChoicePopup)


class ElementGroup(enum.Enum):
    SEARCH = 'used in searches'
    NEW = 'toggled for "new"'
    EDIT = 'toggled for "edit"'


class GroupElement:
    AUTO_SET = mtkf.Element(groups=[ElementGroup.NEW])
    ONLY_EDIT = mtkf.Element(groups=[ElementGroup.EDIT], opt='in')
    ONLY_NEW = mtkf.Element(groups=[ElementGroup.NEW], opt='in')
    NO_SEARCH = mtkf.Element(groups=[ElementGroup.SEARCH])
    ONLY_SEARCH = mtkf.Element(groups=[ElementGroup.SEARCH], opt="in")


class PasswordFormWidget(mtkf.FormWidget):
    password_name = 'password'
    password2_name = 'password2'

    def clean_data(self):
        super().clean_data()
        if self.password_name not in self.data:
            return
        if self.data[self.password_name] != self.data[self.password2_name]:
            self.errors[self.password2_name].add(get_name('error::no_password_match'))
            self.widget_dict[self.password_name].delete(0, tk.END)
            self.widget_dict[self.password2_name].delete(0, tk.END)
        del self.data[self.password2_name]


def form_get_name(form_name):
    """adapt utils.get_name to forms"""
    def inner(name):
        """adapt utils.get_name to forms"""
        if name.endswith('_search_alt'):
            name = name[:-len('_search_alt')]
        return get_name('::'.join(('form', form_name, name)))
    return inner


class BaseForm(mtkf.Form, template=True):
    """Base class for forms.

        handles autocompletes, default content and appropriate get_name handling
    """
    def __init_subclass__(cls, *, template=None, **kwargs):
        form_name = cls.__name__.replace('Form', '')
        cls.get_name = form_get_name(form_name)
        # no .setdefault() :-(
        form_widget = vars(cls).get('FormWidget', type('FormWidget', (), {}))
        form_widget.default_content = config.gui2.entry_defaults.get(form_name).mapping
        form_widget.error_display_options = {}  # workaround
        cls.FormWidget = form_widget
        autocompletes = config.gui2.get('autocomplete').get(form_name)
        for k, v in vars(cls).items():
            if isinstance(v, tuple) and len(v) == 2:
                c, o = v
            else:
                c = v
                o = {}
            if isinstance(c, type) and issubclass(c, tk.Entry):
                values = dict(autocompletes.get(k).mapping)
                if values:
                    c = type('Autocompleted' + c.__name__, (mtk.AutocompleteEntry, c), {})
                    o['autocompletes'] = values
                    setattr(cls, k, (c, o))
        super().__init_subclass__(template=template, **kwargs)

    class FormWidget:
        take_focus = True
        submit_on_return = mtkf.FormWidget.SubmitOnReturn.NOT_FIRST
        submit_button = {'text': get_name('btn_do')}


class SearchForm(BaseForm, template=True):
    """Base class for forms that offer search functionality"""
    class FormWidget(mtkf.FormWidget):
        def submit_action(self, event=None):
            if 'search_mode' in self.widget_dict:
                # hack, I should write something to make me able to access
                # groups on the instance
                w = list(self.widgets)
                for k, v in self.widget_dict.copy().items():
                    value = mtk.get_getter(v)()
                    if not (value or isinstance(value, bool)
                            or k in ['exact_match', 'search_mode']):
                        w.remove(self.widget_dict.pop(k))
                        continue
                    if k.endswith('_search_alt'):
                        del self.widget_dict[k]
                        k = k[:-len('_search_alt')]
                        self.widget_dict[k] = v
                self.widgets = tuple(w)
            super().submit_action(event)

    search_mode: GroupElement.ONLY_SEARCH = (
        mtk.RadioChoiceWidget, {'*args': [(c, get_name(c)) for c in ['and', 'or']]})
    exact_match: GroupElement.ONLY_SEARCH = CheckbuttonWithVar


class BookForm(SearchForm):
    class FormWidget(mtkf.FormWidget):
        def __init__(self, *args, **kwargs):
            """hack"""
            super().__init__(*args, **kwargs)
            self.widget_dict['series_number'] = self.widget_dict['series'].number_dummy

        def clean_data(self):
            """separate series and series_number"""
            super().clean_data()
            if 'series' not in self.data:  # search may remove things
                del self.data['series_number']
                return
            if self.data['series'] is None:
                self.data['series_number'] = None
            else:
                self.data['series'], self.data['series_number'] = self.data['series']
            # TODO: remove this ASAP
            if 'search_mode' in self.widget_dict and self.data['series_number'] is None:
                del self.data['series_number']

    id: GroupElement.ONLY_EDIT = IntEntry

    isbn: mtkf.Element = ISBNEntry
    author: mtkf.Element = (NonEmptyREntry, {'rem_key': 'book-author'})
    title: mtkf.Element = NonEmptyEntry
    series: mtkf.Element = SeriesEntry
    language: mtkf.Element = (NonEmptyREntry, {'rem_key': 'book-language'})
    publisher: mtkf.Element = (NonEmptyREntry, {'rem_key': 'book-publisher'})
    concerned_people: mtkf.Element = (NullREntry, {'rem_key': 'book-cpeople'})
    year: mtkf.Element = IntEntry
    medium: mtkf.Element = (NonEmptyREntry, {'rem_key': 'book-medium'})
    if config.gui2.genres.options is None:
        genres: mtkf.Element = (NullREntry, {'rem_key': 'book-genres'})
    else:
        genres: mtkf.Element = (
            type('StrMultiChoicePopup', (MultiChoicePopup,),
                 {'get': lambda s: s.sep.join(MultiChoicePopup.get(s))}),
            {'options': config.gui2.genres.options,
             'sep': config.gui2.genres.sep}
        )

    library: GroupElement.NO_SEARCH = (OptionsFromSearch, {'action_ns': core.Library})
    library_search_alt: GroupElement.ONLY_SEARCH = (
        OptionsFromSearch, {'action_ns': core.Library, 'allow_none': True})
    groups: mtkf.Element = (SearchMultiChoice, {'action_ns': core.Group})
    shelf: mtkf.Element = (NonEmptyREntry, {'rem_key': 'book-shelf'})


class PersonForm(SearchForm):
    id_: GroupElement.NO_SEARCH = IntEntry
    first_name: mtkf.Element = NonEmptyEntry
    last_name: mtkf.Element = NonEmptyEntry
    class_: mtkf.Element = ClassEntry
    max_borrow: mtkf.Element = IntEntry
    libraries: mtkf.Element = (SearchMultiChoice, {'action_ns': core.Library})
    pay: GroupElement.NO_SEARCH = CheckbuttonWithVar


class MemberForm(SearchForm):
    FormWidget = PasswordFormWidget

    name: mtkf.Element = NonEmptyEntry
    level: mtkf.Element = (mtk.OptionChoiceWidget,
                           {'values': list(utils.level_names.items()),
                            'default': 1})
    current_password: GroupElement.NO_SEARCH = NonEmptyPasswordEntry
    password: GroupElement.ONLY_NEW = NonEmptyPasswordEntry
    password2: GroupElement.ONLY_NEW = NonEmptyPasswordEntry


class ChangePasswordForm(BaseForm):
    class FormWidget(PasswordFormWidget):
        password_name = 'new_password'

    member: mtkf.Element = NonEmptyEntry
    current_password: mtkf.Element = NonEmptyPasswordEntry
    new_password: mtkf.Element = NonEmptyPasswordEntry
    password2: mtkf.Element = NonEmptyPasswordEntry


class LoginForm(BaseForm):
    name: mtkf.Element = NonEmptyEntry
    password: mtkf.Element = NonEmptyPasswordEntry


class LibraryGroupCommon(SearchForm, template=True):
    _position_over_ = True
    name: mtkf.Element = NonEmptyEntry
    books: GroupElement.NO_SEARCH = IntListEntry
    # not as element to allow Library to have a nice order
    action = (mtk.RadioChoiceWidget, {
        '*args': [(a, get_name('form::LibraryGroupCommon::' + a))
                  for a in ['add', 'remove', 'delete']]})


class GroupForm(LibraryGroupCommon):
    action: GroupElement.ONLY_EDIT = LibraryGroupCommon.action


class LibraryForm(LibraryGroupCommon):
    class FormWidget:
        default_content = {'pay_required': True}

    people: GroupElement.NO_SEARCH = IntListEntry
    pay_required: GroupElement.ONLY_NEW = CheckbuttonWithVar
    action: GroupElement.ONLY_EDIT = LibraryGroupCommon.action


class GroupActivationForm(BaseForm):
    group: mtkf.Element = (OptionsFromSearch, {'action_ns': core.Group})
    src: mtkf.Element = (SearchMultiChoice, {'action_ns': core.Library})
    dest: mtkf.Element = (OptionsFromSearch, {'action_ns': core.Library})


class BorrowRestCommonForm(BaseForm, template=True):
    class FormWidget(mtkf.FormWidget):
        def inject_submit(self, **data):
            for k, v in data.items():
                mtk.get_setter(self.widget_dict[k])(v)
            self.submit_action()

    _position_over_ = True
    person: mtkf.Element = IntEntry
    book: mtkf.Element = IntEntry


class BorrowForm(BorrowRestCommonForm):
    weeks: mtkf.Element = IntEntry
    override: mtkf.Element = CheckbuttonWithVar


class RestituteForm(BorrowRestCommonForm):
    pass


class BorrowSearchForm(SearchForm):
    book__id: mtkf.Element = IntEntry
    book__title: mtkf.Element = Entry
    book__author: mtkf.Element = Entry
    book__library: mtkf.Element = (OptionsFromSearch,
                                   {'action_ns': core.Library, 'allow_none': True})
    book__groups: mtkf.Element = (SearchMultiChoice, {'action_ns': core.Group})

    person__id: mtkf.Element = IntEntry
    person__first_name: mtkf.Element = Entry
    person__last_name: mtkf.Element = Entry
    person__class_: mtkf.Element = ClassEntry
    person__libraries: mtkf.Element = (SearchMultiChoice, {'action_ns': core.Library})

    is_back: mtkf.Element = OptionalCheckbuttonWithVar


class ScriptForm(SearchForm):
    name: mtkf.Element = ScriptNameEntry
    permissions: mtkf.Element = (
        FlagEnumMultiChoice,
        {'flag_enum': core.ScriptPermissions, 'get_name_prefix': 'Script::permissions::'}
    )
    setlevel: mtkf.Element = (
        mtk.OptionChoiceWidget,
        {'values': ((None, '-----'), *utils.level_names.items())})
    current_password: GroupElement.NO_SEARCH = NonEmptyPasswordEntry
    code: GroupElement.NO_SEARCH = Text
