"""translate GUI actions to core-provided functions"""

import collections.abc
import enum
import tkinter as tk
from tkinter import ttk
import tkinter.messagebox as tk_msg
import tkinter.font as tk_font
from functools import partial
from typing import Type, Callable, Optional, Sequence, Mapping

from . import main
from . import common
from .. import core
from .. import config
from .. import utils
from .formlib import Form as LibForm, Entry, DropdownChoices, RadioChoices
from .widgets import (
    # not form-related
    SearchResultWidget,
    # generic form widgets and form widget tuples
    NonEmptyEntry, NonEmptyREntry, PasswordEntry, IntEntry, NullREntry, Text,
    ConfirmedPasswordInput, Checkbox, FlagEnumMultiChoice, MultiChoicePopup,
    # specific form widgets and form widget tuples
    SeriesInput, ISBNEntry, ClassEntry, ScriptNameEntry,
    # complex form widgets
    LinkWidget, DisplayWidget, OptionsFromSearch, SearchMultiChoice,
)

Book = common.NSWithLogin(core.Book)
Person = common.NSWithLogin(core.Person)
Library = common.NSWithLogin(core.Library)


class FormTag(enum.Enum):
    SEARCH = '"search" action'
    NEW = '"new" action'
    EDIT = '"edit" action'
    VIEW = '"view" action'


class BaseForm(LibForm):
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
        if isinstance(self.tag, FormTag):
            items = ('form', self.form_name, self.tag.name, name)
        else:
            items = ('form', self.form_name, name)
        print(name, items, utils.get_name('::'.join(items)))
        return utils.get_name('::'.join(items))


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
            return {k: v
                    for k, v in super().get_data().items()
                    if v or isinstance(v, bool)}
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
    """add a 'current_password' field for NEW and EDIT"""
    all_widgets = {
        'current_password': {
            FormTag.NEW: PasswordEntry,
            FormTag.EDIT: PasswordEntry,
        }
    }


class EditForm(BaseForm):
    """Adapt forms for the EDIT action.

    On FormTag.EDIT:
    Use OptionsFromSearch with setter=True for the first not-inherited widget.
    Modify ``.get_data`` to include the value of the first widget under ``'*args'``.
    """
    def __init_subclass__(cls, **kwargs):
        cls.id_name = next(iter(cls.all_widgets))
        super().__init_subclass__(**kwargs)
        widget_spec = cls.all_widgets[cls.id_name]
        if FormTag.EDIT in widget_spec:
            raise TypeError("can't use EditForm if FormTag.EDIT is specified")
        widget_spec[FormTag.EDIT] = (
            OptionsFromSearch,
            common.NSWithLogin(getattr(core, cls.form_name)),
            {'setter': True},
        )

    def get_data(self):
        """put the value of the ID widget under ``'*args'``"""
        data = super().get_data()
        if self.tag is FormTag.EDIT:
            data['*args'] = (data.pop(self.id_name),)
        return data


class ViewForm(BaseForm):
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
            if issubclass(w, (SearchMultiChoice, OptionsFromSearch)):
                ans = a[0] if a else kw.pop('action_ns')
                new = (
                    LinkWidget,
                    partial(view_data, ans.__name__),
                    {'multiple': issubclass(w, SearchMultiChoice)},
                )
            elif issubclass(w, Checkbox):
                new = (Checkbox, {'active': False})
            else:
                display = 'list' if issubclass(w, MultiChoicePopup) else 'str'
                new = (DisplayWidget, display, {})
            ws.setdefault(FormTag.VIEW, new)

    def get_submit_widget(self):
        """Don't show a submit button when used with FormTag.VIEW"""
        if self.tag is FormTag.VIEW:
            return None
        else:
            return super().get_submit_widget()


def form_dialog(root: tk.Widget, form_cls: Type[BaseForm]) -> Optional[dict]:
    """Show a pop-up dialog based on a form"""
    def callback(kwargs):
        nonlocal data
        data = kwargs
        popup.destroy()

    data = None
    popup = tk.Toplevel(root)
    try:
        popup.transient(root)
        popup.grab_set()
        form_cls(popup, None, callback)
        popup.wait_window()
    except Exception:
        popup.destroy()
        raise
    return data


def callback_adapter(callback, do_reset, kwargs):
    """Adapter for form callbacks <-> ActionNS actions. For use with functools.partial.

    The adapter handles argument unpacking (including *args) and error displaying.
    These first two arguments should be given beforehand:
    :param callback: is the action to wrap
    :param do_reset: specifies whether ``app.reset`` should be called after the callback
    The final argument should then be provided by the form:
    :param kwargs: form submission data to call the real callback with
    """
    args = kwargs.pop('*args', ())
    try:
        callback(*args, **kwargs)
    except core.BuchSchlossBaseError as e:
        tk_msg.showerror(e.title, e.message)
    except Exception:
        tk_msg.showerror(None, utils.get_name('unexpected_error'))
        raise
    else:
        if do_reset:
            main.app.reset()


def make_action(master: tk.Widget,
                name: str,
                func: str,
                ans: Type[core.ActionNamespace] = None,
                ) -> Callable:
    """Make actions from a form and function name

    :param master: is the master widget (passed to the form)
    :param name: is the form name without 'Form'-suffix, e.g. 'book'
    :param func: is the name of the function.
      'search' is handled by :func:`.search_callback`
      'view' is redirected to :func:`.view_action`
    :param ans: is the ActionNamespace to use. If None, ``name`` is used to
      select one automatically (must exist)
    """
    if ans is None:
        ans = getattr(core, name.capitalize())
    ans = common.NSWithLogin(ans)
    form_cls = globals().get(
        f'{name.capitalize()}{func.title().replace("_", "")}Form',
        globals()[name.capitalize() + 'Form']
    )
    tag = FormTag.__members__.get(func.upper())
    if func == 'view':
        return partial(view_action, master, ans)
    if func == 'search':
        view_func = partial(view_data, name)
        middle_callback = partial(search_callback, master, view_func, ans)
        callback = partial(callback_adapter, middle_callback, False)
    else:
        callback = partial(callback_adapter, getattr(ans, func), True)
    return partial(form_cls, master, tag, callback)


def show_results(master: tk.Widget,
                 results: Sequence,
                 view_func: Callable[[tk.Widget, core.DataNamespace], None],
                 ):
    """show search results as buttons taking the user to the appropriate view

    :param master: is the master widget in which the results are displayed
    :param results: is a sequence of DataNS objects
    :param view_func: is a function that displays data
    """

    def search_show():
        common.destroy_all_children(search_frame)
        SearchResultWidget(search_frame, results, view_wrap).pack()

    def view_wrap(dns):
        common.destroy_all_children(search_frame)
        tk.Button(
            search_frame,
            text=utils.get_name('back_to_results'),
            command=search_show,
        ).pack()
        result_frame = tk.Frame(search_frame)
        result_frame.pack()
        return view_func(result_frame, dns)

    common.destroy_all_children(master)
    search_frame = tk.Frame(master)
    search_frame.pack()
    search_show()


def search_callback(master: tk.Widget,
                    view_func: Callable[[tk.Widget, core.DataNamespace], None],
                    ans: common.NSWithLogin,
                    search_mode: str,
                    exact_match: bool,
                    **kwargs,
                    ):
    """Provide a search-specific callback. Intended for use with ``functools.partial``.

    This callback displays the search results with :func:`.show_results`.
    These arguments are meant to be given beforehand:
    :param master: is passed to :func:`.show_results`
    :param view_func: is passed to :func:`.show_results`
    :param ans: is the (wrapped) ActionNamespace used for searching
      and getting result DataNamespaces

    These arguments typically are provided by the form submission:
    :param search_mode: is ``'and'`` or ``'or'`` and specifies how the different
      values are combined into a search query
    :param exact_match: specified whether to use ``'eq'`` or ``'contains'`` operators
    :param kwargs: are the search queries
    """
    q = ()
    for k, val_seq in kwargs.items():
        k = k.replace('__', '.')
        if (isinstance(val_seq, str)
                or not isinstance(val_seq, collections.abc.Sequence)):
            val_seq = [val_seq]
        for v in val_seq:
            if exact_match or not isinstance(v, str):
                q = ((k, 'eq', v), search_mode, q)
            else:
                q = ((k, 'contains', v), search_mode, q)

    def wrapped_view(view_master, dns):
        """wrap to get a complete DataNS"""
        return view_func(view_master, ans.view_ns(dns['id']))

    show_results(master, tuple(ans.search(q)), wrapped_view)


def view_data(name: str, master: tk.Widget, dns: core.DataNamespace):
    """Display data. Useful with ``functools.partial``.

    :param name: is a :func:`.make_action`-compatible name
    :param master: is the master widget to display data in
    :param dns: is a DataNamespace of the object to display
    """
    for child in master.children.copy().values():
        child.destroy()
    form_cls: Type[BaseForm] = globals()[name.capitalize() + 'Form']
    form = form_cls(master, FormTag.VIEW, lambda **kw: None)
    try:
        form.set_data(dns)
    except core.BuchSchlossBaseError as e:
        tk_msg.showerror(e.title, e.message)
    except Exception:
        tk_msg.showerror(None, utils.get_name('unexpected_error'))
        raise


def view_action(master: tk.Widget, ans: common.NSWithLogin):
    """Ask for an ID and call :func:`.view_data`. Useful with ``functools.partial``"""
    temp_form = type(
        ans.ans.__name__ + 'Form',
        (BaseForm,),
        {'all_widgets': {'id': (OptionsFromSearch, ans, {})}},
    )
    result = form_dialog(master.winfo_toplevel(), temp_form)  # noqa
    if result is None:
        main.app.reset()
        return
    view_data(ans.ans.__name__, master, ans.view_ns(result['id']))


def login_logout():
    """log in or log out"""
    if main.app.current_login.type is core.LoginType.GUEST:
        data = form_dialog(main.app.root, LoginForm)
        if data is None:
            return
        try:
            main.app.current_login = core.login(**data)
        except core.BuchSchlossBaseError as e:
            tk_msg.showerror(e.title, e.message)
            return
        main.app.header.set_info_text(
            utils.get_name('logged_in_as_{}').format(
                utils.get_name('Member[{}]({})').format(
                    main.app.current_login.name,
                    utils.level_names[main.app.current_login.level])))
        main.app.header.set_login_text(utils.get_name('action::logout'))
    else:
        main.app.current_login = core.guest_lc
        main.app.header.set_info_text(utils.get_name('logged_out'))
        main.app.header.set_login_text(utils.get_name('action::login'))


def display_lua_data(data):
    """provide a callback for lua's display"""
    popup = tk.Toplevel(main.app.root)
    popup.transient(main.app.root)
    popup.grab_set()
    frame = tk.Frame(popup, **config.gui2.widget_size.popup.mapping)
    frame.propagate(False)
    frame.grid(row=0, column=0)
    view = ttk.Treeview(frame)
    height, width = add_lua_data_entries(view, '', data)
    view.column('#0', width=width)
    if height > view['height']:
        sb = tk.Scrollbar(popup, command=view.yview, orient=tk.VERTICAL)
        sb.grid(row=0, column=1, anchor=tk.NS)
        view['yscrollcommand'] = sb.set
    if width > config.gui2.widget_size.popup.width:
        sb = tk.Scrollbar(popup, command=view.xview, orient=tk.HORIZONTAL)
        sb.grid(row=1, column=0, anchor=tk.EW)
        view['xscrollcommand'] = sb.set
    tk.Button(popup, command=popup.destroy, text='OK').pack()


def add_lua_data_entries(view, parent, data, width=0, height=0, indent=1):
    """add entries to the Treeview and return (max width, total height)"""
    if isinstance(data, Sequence) and not isinstance(data, str):
        data = enumerate(data, 1)
    elif isinstance(data, Mapping):
        data = data.items()
    else:
        data = ((data, ()),)
    for name, sub in data:
        width = max(width, tk_font.nametofont('TkDefaultFont').measure(name) + 25*indent)
        child = view.insert(parent, tk.END, text=name)
        width, height = add_lua_data_entries(view, child, sub, width, height+1, indent+1)
    return width, height


def handle_lua_get_data(data_spec):
    """provide a callback for lua's get_data"""
    type_widget_map = {
        'int': IntEntry,
        'bool': Checkbox,
        'str': Entry,
    }
    def get_name(internal):
        try:
            return name_data[internal]
        except KeyError:
            # only happens on errors
            return utils.get_name('form::' + internal)
    name_data = {'submit': utils.get_name('form::submit')}
    cls_body = {'get_name': staticmethod(get_name), 'all_widgets': {}}
    for k, name, v in data_spec:
        cls_body['all_widgets'][k] = type_widget_map[v]
        name_data[k] = name
    form_cls = type('LuaGetDataForm', (BaseForm,), cls_body)
    common.destroy_all_children(main.app.center)
    watcher = tk.Variable()
    data = None
    def cb(new):
        nonlocal data
        data = new
        watcher.set('set')
    main.app.on_next_reset.append(lambda: watcher.set('set'))
    form = form_cls(main.app.center, None, cb)
    form.frame.wait_variable(watcher)
    return data


def get_script_action(script_spec):
    """prepare a lua script action"""
    # login_context must be passed at call time
    def action():
        try:
            utils.get_script_target(
                script_spec,
                ui_callbacks=main.lua_callbacks,
                login_context=main.app.current_login,
                propagate_bse=True,
            )()
        except core.BuchSchlossBaseError as e:
            tk_msg.showerror(e.title, e.message)
        finally:
            main.app.reset()

    return action

# NOTE: the following functions aren't used anywhere
# the decorator registers them in common.NSWithLogin


@common.NSWithLogin.override('Book', 'new')
def book_new(**kwargs):
    tk_msg.showinfo(
        utils.get_name('Book'),
        utils.get_name('Book::new_id_{}').format(
            core.Book.new(login_context=main.app.current_login, **kwargs))
    )


@common.NSWithLogin.override('Book', 'search')
def book_search(condition):
    return core.Book.search(
        (condition, 'and', ('is_active', 'eq', True)),
        login_context=main.app.current_login,
    )


@common.NSWithLogin.override('Borrow', 'restitute')
def borrow_restitute(book):
    core.Borrow.edit(
        common.NSWithLogin(core.Book).view_ns(book).borrow,
        is_back=True,
        login_context=main.app.current_login,
    )


@common.NSWithLogin.override('Borrow', 'extend')
def borrow_extend(book, weeks):
    core.Borrow.edit(
        common.NSWithLogin(core.Book).view_ns(book).borrow,
        weeks=weeks,
        login_context=main.app.current_login,
    )


# Form definitions


class BookForm(SearchForm, EditForm, ViewForm):
    all_widgets = {
        'id': {FormTag.VIEW: DisplayWidget},
        'isbn': {
            FormTag.NEW: (ISBNEntry, True, {}),
            None: (ISBNEntry, False, {}),
        },
        'author': NonEmptyREntry,
        'title': NonEmptyEntry,
        'series': SeriesInput,
        'series_number': SeriesInput.NumberDummy,
        'language': NonEmptyREntry,
        'publisher': NonEmptyREntry,
        'concerned_people': NullREntry,
        'year': IntEntry,
        'medium': NonEmptyREntry,
        'borrow': {FormTag.VIEW: (
            LinkWidget,
            partial(view_data, 'person'),
            {'attr': 'person'},
        )},
        'genres': (MultiChoicePopup, lambda: Book.get_all_genres(), {}),
        'library': {
            None: (OptionsFromSearch, Library, {}),
            FormTag.SEARCH: (OptionsFromSearch, Library, {'allow_none': True}),
        },
        'groups': (MultiChoicePopup, lambda: Book.get_all_groups(), {}),
        'shelf': NonEmptyREntry,
    }


class PersonForm(SearchForm, EditForm, ViewForm):
    all_widgets = {
        'id_': {
            FormTag.SEARCH: None,
            FormTag.NEW: IntEntry,
        },
        'first_name': NonEmptyREntry,
        'last_name': NonEmptyREntry,
        'class_': ClassEntry,
        'max_borrow': IntEntry,
        'borrows': {FormTag.VIEW: (
            LinkWidget,
            partial(view_data, 'book'),
            {'attr': 'book', 'multiple': True},
        )},
        'libraries': (SearchMultiChoice, Library, {}),
        'pay': {
            FormTag.SEARCH: None,
            FormTag.VIEW: None,
            None: Checkbox,
        },
        'borrow_permission': {FormTag.VIEW: DisplayWidget},
    }


class MemberForm(AuthedForm, SearchForm, EditForm, ViewForm):
    all_widgets = {
        'name': NonEmptyREntry,
        'level': (DropdownChoices, tuple(utils.level_names.items()), 1, {}),
        'password': {FormTag.NEW: ConfirmedPasswordInput},
    }


class MemberChangePasswordForm(AuthedForm):
    all_widgets = {
        'member': (OptionsFromSearch, common.NSWithLogin(core.Member), {}),
        'current_password': PasswordEntry,
        'new_password': ConfirmedPasswordInput,
    }


class LoginForm(BaseForm):
    all_widgets = {
        'name': NonEmptyREntry,
        'password': PasswordEntry,
    }


class LibraryForm(SearchForm, EditForm, ViewForm):
    all_widgets = {
        'name': NonEmptyREntry,
        'pay_required': Checkbox,
    }


class BorrowForm(ViewForm):
    # NOTE: this form is actually only used for NEW and VIEW
    # EDIT is split into restitute + extend, SEARCH is separate
    all_widgets = {
        'person': (OptionsFromSearch, Person, {}),
        'book': (OptionsFromSearch, Book, {}),
        'weeks': {FormTag.NEW: IntEntry},
        'override': {FormTag.NEW: Checkbox},
        'return_date': {FormTag.VIEW: DisplayWidget},
    }


class BorrowRestituteForm(BaseForm):
    all_widgets = {
        'book': (OptionsFromSearch, Book,
                 {'condition': ('borrow.is_back', 'eq', False)}),
    }


class BorrowExtendForm(BaseForm):
    all_widgets = {
        'book': (OptionsFromSearch, Book,
                 {'condition': ('borrow.is_back', 'eq', False)}),
        'weeks': IntEntry,
    }


class BorrowSearchForm(SearchForm):
    all_widgets = {
        'book__title': NullREntry,
        'book__author': NullREntry,
        'book__library': (OptionsFromSearch, Library, {'allow_none': True}),
        'book__groups': (MultiChoicePopup, lambda: Book.get_all_groups(), {}),
        # this has on_empty='error', but empty values are removed when searching
        # the Null*Entries above are not really needed
        'person__class_': ClassEntry,
        'person__libraries': (SearchMultiChoice, Library, {}),
        'is_back': (Checkbox, {'allow_none': True}),
    }


class ScriptForm(AuthedForm, SearchForm, EditForm, ViewForm):
    all_widgets = {
        'name': ScriptNameEntry,
        'permissions': (FlagEnumMultiChoice, core.ScriptPermissions, {}),
        'setlevel': (DropdownChoices,
                     ((None, '-----'), *utils.level_names.items()), {}),
        'code': {
            None: Text,
            FormTag.SEARCH: None,
            FormTag.VIEW: None,
        }
    }
