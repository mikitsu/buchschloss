"""translate GUI actions to core-provided functions"""

import collections.abc
import itertools
import tkinter as tk
import tkinter.messagebox as tk_msg
from functools import partial
import typing as T
from typing import Type, Callable, Any, Iterable, Optional

from ..misc import tkstuff as mtk
from ..misc.tkstuff import dialogs as mtkd
from ..misc.tkstuff import forms as mtkf
from . import main
from . import formlib
from . import widgets
from . import common
from .. import core
from .. import config
from .. import utils
from .widgets import (
    BaseForm, AuthedForm, EditForm, SearchForm, ViewForm, FormTag,
    ISBNEntry, NonEmptyEntry, NonEmptyREntry, ClassEntry, PasswordEntry,
    IntEntry, NullREntry, Text, ConfirmedPasswordInput, DisplayWidget,
    Checkbox, SeriesInput, OptionsFromSearch, search_multi_choice,
    FlagEnumMultiChoice, ScriptNameEntry, MultiChoicePopup, LinkWidget,
)


def form_dialog(root: tk.Widget, form_cls: Type[BaseForm]) -> Optional[dict]:
    """Show a pop-up dialog based on a form"""
    def callback(**kwargs):
        nonlocal data
        data = kwargs
        popup.destroy()

    data = None
    popup = tk.Toplevel(root)
    popup.transient(root)
    form_cls(popup, None, callback)
    popup.mainloop()
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
    form_cls = globals()[name.capitalize() + 'Form']
    tag = FormTag.__members__.get(func.upper())
    if func == 'view':
        return partial(view_action, master, ans)
    if func == 'search':
        view_func = partial(view_data, name)
        middle_callback = partial(search_callback, master, view_func, ans.search)
        callback = partial(callback_adapter, middle_callback, False)
    else:
        callback = partial(callback_adapter, getattr(ans, func), True)
    return partial(form_cls, master, tag, callback)


def show_results(master: tk.Widget,
                 results: Iterable,
                 view_func: Callable[[tk.Widget, core.DataNamespace], None],
                 ):
    """show search results as buttons taking the user to the appropriate view

    :param master: is the master widget in which the results are displayed
    :param results: is an iterable of objects as those returned by ``ANS.search``
    :param view_func: is a function that displays data
    """

    def search_hide():
        rw.pack_forget()
        show_btn = tk.Button(search_frame, text=utils.get_name('back_to_results'))
        show_btn.config(command=partial(search_show, show_btn))
        show_btn.pack()

    def search_show(btn):
        btn.destroy()
        ShowInfo.to_destroy.container.destroy()
        ShowInfo.to_destroy = None
        rw.pack()

    def view_wrap(dns):
        search_hide()
        return view_func(search_frame, dns)

    search_frame = tk.Frame(master)
    search_frame.pack()
    rw = widgets.SearchResultWidget(search_frame, tuple(results), view_wrap)
    rw.pack()


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
        return view_func(view_master, ans.view_ns(dns.id))

    show_results(master, ans.search(q), wrapped_view)


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
    form.set_data({k: getattr(dns, k) for k in dir(dns)})  # TODO: make DataNS a mapping


def view_action(master: tk.Widget, ans: common.NSWithLogin):
    """Ask for an ID and call :func:`.view_data`. Useful with ``functools.partial``"""
    temp_form = type(
        ans.ans.__name__ + 'Form',
        (BaseForm,),
        {'all_widgets': {'id': (OptionsFromSearch, ans.ans, {})}},
    )
    id_ = form_dialog(master.winfo_toplevel(), temp_form)  # noqa
    if id_ is None:
        main.app.reset()
        return
    view_data(ans.ans.__name__, master, ans.view_ns(id_))


class ShowInfo:
    """provide callables that display information"""
    to_destroy: T.ClassVar[T.Optional[tk.Widget]] = None
    instances: T.ClassVar[T.Dict[str, 'ShowInfo']]
    SpecialKeyFunc = T.Callable[[dict], T.Optional[T.Sequence]]

    def __init__(
            self,
            namespace: T.Type[core.ActionNamespace],
            special_keys: T.Mapping[str, SpecialKeyFunc] = {},  # noqa
            id_type: type = str,
        ):  # noqa
        """Initialize

        :param namespace: the action namespace to use for getting information
        :param special_keys: a mapping from keys in the returned data to a function
            taking the value mapped by the key and returning anew key
            (may be None to use the default) and a value to pass
            to widgets.InfoWidget.
        :param id_type: the type of the ID
        """
        self.action_ns = common.NSWithLogin(namespace)
        self.special_keys = special_keys
        self.id_type = id_type
        self.get_name_prefix = namespace.__name__ + '::'

    def __call__(self, id_=None):
        """ask for ID if not given"""
        if id_ is None:
            id_get_text = utils.get_name(self.get_name_prefix + 'id')
            try:
                id_ = mtkd.WidgetDialog.ask(
                    main.app.root,
                    widgets.OptionsFromSearch,
                    {'action_ns': self.action_ns.ans},
                    title=id_get_text,
                    text=id_get_text,
                )
            except mtkd.UserExitedDialog:
                main.app.reset()
                return
        self.display_information(id_)

    def display_information(self, id_):
        """actually display information"""
        if ShowInfo.to_destroy is not None:
            ShowInfo.to_destroy.container.destroy()
        try:
            data = self.action_ns.view_str(id_)
        except core.BuchSchlossBaseError as e:
            tk_msg.showerror(e.title, e.message)
            main.app.reset()
            return
        pass_widgets = {utils.get_name('info_regarding'): data['__str__']}
        for k, v in data.items():
            display = utils.get_name(self.get_name_prefix + k)
            if k in self.special_keys:
                v = self.special_keys[k](data)
                pass_widgets[display] = v
            elif '_id' not in k and k != '__str__':
                pass_widgets[display] = str(v)
        iw = widgets.InfoWidget(main.app.center, pass_widgets)
        iw.pack()
        ShowInfo.to_destroy = iw


ShowInfo.instances = {
    'Book': ShowInfo(
        core.Book,
        {'borrowed_by': lambda d:
            (widgets.Button, {
                'text': d['borrowed_by'],
                'command': (partial(ShowInfo.instances['Person'], d['borrowed_by_id'])
                            if d['borrowed_by_id'] is not None else None)
            })
         },
        int,
    ),
    'Person': ShowInfo(
        core.Person,
        {'borrows': lambda d:
            [(widgets.Button, {
                'text': t,
                'command': partial(ShowInfo.instances['Book'], i)})
             for t, i in zip(d['borrows'], d['borrow_book_ids'])],
         },
        int,
    ),
    'Borrow': ShowInfo(
        core.Borrow,
        {'person': lambda d:
            (widgets.Button, {
                'text': d['person'],
                'command': partial(ShowInfo.instances['Person'], d['person_id'])
            }),
         'book': lambda d:
             (widgets.Button, {
                 'text': d['book'],
                 'command': partial(ShowInfo.instances['Book'], d['book_id'])
             }),
         },
        int,
    ),
}
ShowInfo.instances.update({k: ShowInfo(getattr(core, k))
                           for k in ('Library', 'Member', 'Script')})


def login():
    """log in"""
    if main.app.current_login.type is core.LoginType.GUEST:
        try:
            data = mtkd.FormDialog.ask(main.app.root, forms.LoginForm)
        except mtkd.UserExitedDialog:
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
    widget_cls, kwargs = get_lua_data_widget(popup, data)
    widget_cls = mtk.ScrollableWidget(**config.gui2.widget_size.popup.mapping)(widget_cls)
    widget_cls(popup, *kwargs.pop('*args', ()), **kwargs).pack()
    tk.Button(popup, command=popup.destroy, text='OK').pack()


def get_lua_data_widget(master, data):
    """recursively create a widget for lua display callback"""
    if isinstance(data, dict):
        return (mtk.ContainingWidget,
                {'*args': itertools.chain(*(((tk.Label, {'text': k}),
                                            get_lua_data_widget(master, v))
                                            for k, v in data.items())),
                 'horizontal': 2})
    elif isinstance(data, T.Sequence) and not isinstance(data, str):
        return (mtk.ContainingWidget,
                {'*args': [get_lua_data_widget(master, d) for d in data],
                 'direction': (tk.BOTTOM, tk.RIGHT)})
    else:
        return (tk.Label, {'text': data})


def handle_lua_get_data(data_spec):
    """provide a callback for lua's get_data"""
    type_widget_map = {
        'int': widgets.IntEntry,
        'bool': widgets.CheckbuttonWithVar,
        'str': tk.Entry,
    }
    name_data = {}
    cls_body = {'get_name': name_data.__getitem__}
    for k, name, v in data_spec:
        cls_body[k] = mtkf.Element(type_widget_map[v])
        name_data[k] = name
    form = type('Cli2DataForm', (mtkf.Form,), cls_body)
    try:
        return mtkd.FormDialog.ask(main.app.root, form)
    except mtkd.UserExitedDialog:
        return None


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
        main.app.reset()

    return action

# NOTE: the following functions aren't used anywhere
# the decorator registers them in common.NSWithLogin


@common.NSWithLogin.override('Book', 'new')  # actually used because it's shorter
def new_book(**kwargs):
    tk_msg.showinfo(
        utils.get_name('Book'),
        utils.get_name('Book::new_id_{}').format(
            core.Book.new(login_context=main.app.current_login, **kwargs))
    )


@common.NSWithLogin.override('Borrow', 'restitute')
def borrow_restitute(book):
    core.Borrow.edit(
        common.NSWithLogin(core.Book).view_ns(book),
        is_back=True,
        login_context=main.app.current_login,
    )


@common.NSWithLogin.override('Borrow', 'extend')
def borrow_extend(book, weeks):
    core.Borrow.edit(
        common.NSWithLogin(core.Book).view_ns(book),
        weeks=weeks,
        login_context=main.app.current_login,
    )


# Form definitions


class BookForm(SearchForm, EditForm):
    all_widgets = {
        'id': {},
        'isbn': {
            FormTag.NEW: (ISBNEntry, True, {}),
            None: (ISBNEntry, False, {}),
        },
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


class PersonForm(SearchForm, EditForm):
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


class MemberForm(AuthedForm, SearchForm, EditForm):
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


class LibraryForm(SearchForm, EditForm):
    all_widgets = {
        'name': NonEmptyREntry,
        'books': {FormTag.SEARCH: None,
                  None: search_multi_choice(core.Book)},
        'people': {FormTag.SEARCH: None,
                   None: search_multi_choice(core.Person)},
        'pay_required': Checkbox,
        'action': {
            FormTag.EDIT: (
                formlib.DropdownChoices,
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


class ScriptForm(AuthedForm, SearchForm, EditForm):
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
