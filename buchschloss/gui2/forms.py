"""forms"""

import tkinter as tk
import enum

from ..misc import tkstuff as mtk
from ..misc.tkstuff import forms as mtkf

from buchschloss import config
from buchschloss.utils import get_name

from .widgets import (ISBNEntry, NonEmptyEntry, NonEmptyREntry, ClassEntry,
                      IntEntry, NullREntry, ListEntry, ListREntry,
                      IntListEntry, NonEmptyPasswordEntry, Entry,
                      OptionalCheckbuttonWithVar, CheckbuttonWithVar,
                      SeriesEntry)


class ElementGroup(enum.Enum):
    SEARCH = 'used in searches'
    NEW = 'toggled for "new"'
    EDIT = 'toggled for "edit"'


class GroupElement:
    AUTO_SET = mtkf.Element(groups=[ElementGroup.NEW])
    ONLY_EDIT = mtkf.Element(groups=[ElementGroup.EDIT], opt='in')
    ONLY_NEW = mtkf.Element(groups=[ElementGroup.NEW], opt='in')
    NO_SEARCH = mtkf.Element(groups=[ElementGroup.SEARCH])


class PasswordFormWidget(mtkf.FormWidget):
    password_name = 'password'
    password2_name = 'password2'

    def clean_data(self):
        super().clean_data()
        if self.data[self.password_name] != self.data[self.password2_name]:
            self.errors[self.password2_name].add(get_name('error_password_match'))
            self.widget_dict[self.password_name].delete(0, tk.END)
            self.widget_dict[self.password2_name].delete(0, tk.END)
        del self.data[self.password2_name]


class BaseForm(mtkf.Form, template=True):
    def __init_subclass__(cls, *, template=None, **kwargs):
        autocompletes = config.gui2.get('autocomplete').get(cls.__name__.replace('Form', ''))
        for k, v in vars(cls).items():
            if isinstance(v, tuple) and len(v) == 2:
                c, o = v
            else:
                c = v
                o = {}
            if isinstance(c, type) and issubclass(c, tk.Entry):
                values = autocompletes.get(k).mapping
                if values:
                    c = type('Autocompleted'+c.__name__, (mtk.AutocompleteEntry, c), {})
                    o['autocompletes'] = values
                    setattr(cls, k, (c, o))
        super().__init_subclass__(template=template, **kwargs)

    class FormWidget:
        take_focus = True
        submit_on_return = mtkf.FormWidget.SubmitOnReturn.ALL
        submit_button = {'text': get_name('btn_do')}
        # workaround, this isn't needed if we decide to update misc
        error_display_options = {'popup_field_name_resolver': get_name}

    get_name = get_name


class SearchableForm(BaseForm, template=True):
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
                self.widgets = tuple(w)
            super().submit_action(event)

    search_mode: mtkf.Element(groups=[ElementGroup.SEARCH], opt="in") = (
        mtk.RadioChoiceWidget, {'*args': [(c, get_name(c)) for c in ['and', 'or']]})
    exact_match: mtkf.Element(groups=[ElementGroup.SEARCH], opt='in') = CheckbuttonWithVar


class BookForm(SearchableForm):
    class FormWidget(mtkf.FormWidget):
        default_content = config.gui2.get('entry defaults').get('Book').mapping

        def __init__(self, *args, **kwargs):
            """hack"""
            super().__init__(*args, **kwargs)
            self.widget_dict['series_number'] = self.widget_dict['series'].number_dummy

        def clean_data(self):
            """separate series and series_number"""
            super().clean_data()
            if self.data['series'] is None:
                self.data['series_number'] = None
            else:
                self.data['series'], self.data['series_number'] = self.data['series']

    id: GroupElement.ONLY_EDIT = IntEntry

    isbn: mtkf.Element = ISBNEntry
    author: mtkf.Element = (NonEmptyREntry, {'rem_key': 'book-author'})
    title: mtkf.Element = NonEmptyEntry
    series: mtkf.Element = SeriesEntry
    language: mtkf.Element = NonEmptyEntry
    publisher: mtkf.Element = NonEmptyEntry
    concerned_people: mtkf.Element = (NullREntry, {'rem_key': 'book-cpeople'})
    year: mtkf.Element = IntEntry
    medium: mtkf.Element = NonEmptyEntry
    genres: mtkf.Element = (NullREntry, {'rem_key': 'book-genres'})

    library: mtkf.Element = NonEmptyEntry
    groups: mtkf.Element = (ListREntry, {'rem_key': 'book-groups'})
    shelf: mtkf.Element = (NonEmptyREntry, {'rem_key': 'book-shelf'})


class PersonForm(SearchableForm):
    class FormWidget:
        default_content = config.gui2.get('entry defaults').get('Person').mapping

    def get_name(name: str):
        if name == 'id':
            return get_name('s_nr')
        else:
            return get_name(name)

    id: GroupElement.NO_SEARCH = IntEntry
    first_name: mtkf.Element = NonEmptyEntry
    last_name: mtkf.Element = NonEmptyEntry
    class_: mtkf.Element = ClassEntry
    max_borrow: mtkf.Element = IntEntry
    libraries: mtkf.Element = ListEntry
    pay: GroupElement.NO_SEARCH = CheckbuttonWithVar


class MemberForm(BaseForm):
    class FormWidget(PasswordFormWidget):
        def clean_data(self):
            try:
                super().clean_data()
            except KeyError as e:
                pass
            if 'edit_password_button' in self.data:
                del self.data['edit_password_button']

    name: mtkf.Element = NonEmptyEntry
    level: mtkf.Element = (mtk.OptionChoiceWidget,
                           {'values': get_name('level_list'),
                            'default': 1})
    current_password: mtkf.Element = NonEmptyPasswordEntry
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


class LibraryGroupCommon(BaseForm, template=True):
    _position_over_ = True
    name: mtkf.Element = NonEmptyEntry
    books: mtkf.Element = IntListEntry
    # not as element to allow Library to have a nice order
    action = (mtk.RadioChoiceWidget, {'*args': [(a, get_name(a)) for a in
                                                ['add', 'remove', 'delete']]})


class GroupForm(LibraryGroupCommon):
    action: GroupElement.ONLY_EDIT = LibraryGroupCommon.action


class LibraryForm(LibraryGroupCommon):
    class FormWidget:
        default_content = {'pay_required': True}

    people: mtkf.Element = IntListEntry
    pay_required: GroupElement.ONLY_NEW = CheckbuttonWithVar
    action: GroupElement.ONLY_EDIT = LibraryGroupCommon.action


class GroupActivationForm(BaseForm):
    name: mtkf.Element = NonEmptyEntry
    src: mtkf.Element = ListEntry
    dest: mtkf.Element = Entry


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
    class FormWidget:
        default_content = {'borrow_time': '4'}

    borrow_time: mtkf.Element = IntEntry


class RestituteForm(BorrowRestCommonForm):
    pass


class BorrowSearchForm(SearchableForm):
    book__id: mtkf.Element = IntEntry
    book__library: mtkf.Element = Entry
    book__groups: mtkf.Element = Entry

    person__s_nr: mtkf.Element = IntEntry
    person__first_name: mtkf.Element = Entry
    person__last_name: mtkf.Element = Entry
    person__class_: mtkf.Element = ClassEntry
    person__libraries: mtkf.Element = ListEntry

    is_back: mtkf.Element = OptionalCheckbuttonWithVar
