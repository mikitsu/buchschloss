"""translate GUI actions to core-provided functions"""

import collections.abc
import enum
import logging
import tkinter as tk
from tkinter import ttk
import tkinter.messagebox as tk_msg
import tkinter.font as tk_font
from functools import partial
from typing import Type, Callable, Optional, Sequence, Mapping, Any, ClassVar

from . import main
from . import common
from .. import core
from .. import config
from .. import utils
from ..aforms import Widget as W, FormTag
from .formlib import Form as LibForm, ScrolledForm
from . import widgets
from .widgets import WRAPLENGTH


NonEmptyEntry = (W.ENTRY, 'error', {'max_history': 0})
NonEmptyREntry = (W.ENTRY, 'error', {})
ClassEntry = (W.ENTRY, 'error', {'regex': config.gui2.class_regex})
IntEntry = (W.ENTRY, 'error', {'transform': int})
NullIntEntry = (W.ENTRY, 'none', {'transform': int})
NullEntry = (W.ENTRY, 'none', {'max_history': 0})
NullREntry = (W.ENTRY, 'none', {})
ScriptNameEntry = (W.ENTRY, 'error', {'regex': r'^[a-zA-Z0-9 _-]*$'})
PasswordEntry = (W.ENTRY, 'keep', {'extra_kwargs': {'show': '*'}})


class NSForm(LibForm):
    widget_ns = widgets


class BaseForm(NSForm, ScrolledForm):
    """Base class for forms, handling default content and autocompletes"""
    height = config.gui2.widget_size.main.height

    def __init__(self, frame, tag, submit_callback):
        super().__init__(frame, tag, submit_callback)
        if tag is FormTag.NEW:
            self.set_data(config.gui2.entry_defaults.get(self.form_name).mapping)

    def __init_subclass__(cls, **kwargs):
        """Handle autocompletes"""
        # This will put every widget spec into the standard form, required below
        super().__init_subclass__(**kwargs)

        for k, v in config.gui2.get('autocomplete').get(cls.form_name).mapping.items():
            warn = True
            if k in cls.all_widgets:
                for w, *_, w_kwargs in cls.all_widgets[k].values():
                    if w is W.ENTRY:  # TODO: do we want this for differently-named entries?
                        warn = False
                        w_kwargs.setdefault('autocomplete', v)
            if warn:
                logging.warning(
                    f'autocomplete for {cls.form_name}.{k} specified, but no applied')

    def get_widget_label(self, widget):
        """add ``wraplength``"""
        label = super().get_widget_label(widget)
        if label is not None:
            label['wraplength'] = WRAPLENGTH
        return label


class SearchForm(BaseForm):
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
        return errors


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
    id_name: ClassVar[str]

    def __init_subclass__(cls, **kwargs):
        cls.id_name = next(iter(cls.all_widgets))
        super().__init_subclass__(**kwargs)
        widget_spec = cls.all_widgets[cls.id_name]
        if FormTag.EDIT in widget_spec:
            raise TypeError("can't use EditForm if FormTag.EDIT is specified")
        widget_spec[FormTag.EDIT] = (
            W.OPTIONS_FROM_SEARCH,
            getattr(core, cls.form_name),
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
            if w in (W.SEARCH_MULTI_CHOICE, W.OPTIONS_FROM_SEARCH):
                ans = a[0] if a else kw.pop('action_ns')
                new = (
                    W.LINK,
                    partial(view_data, ans.__name__),
                    {'multiple': w is W.SEARCH_MULTI_CHOICE},
                )
            elif w is W.CHECKBOX:
                new = (W.CHECKBOX, {'active': False})
            else:
                display = 'list' if w is W.MULTI_CHOICE_POPUP else 'str'
                new = (W.DISPLAY, display, {})
            ws.setdefault(FormTag.VIEW, new)

    def get_submit_widget(self):
        """Don't show a submit button when used with FormTag.VIEW"""
        if self.tag is FormTag.VIEW:
            return None
        else:
            return super().get_submit_widget()


class SearchResultForm(BaseForm):
    """Pseudo-form for displaying search results. Subclass setting ``all_widgets``"""
    def get_widget_label(self, widget):
        """No labels for search results"""
        return None

    def get_submit_widget(self):
        """no submit widget"""
        return None


def form_dialog(root: tk.Widget, form_cls: Type[NSForm]) -> Optional[dict]:
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
    if not results:
        tk_msg.showinfo(utils.get_name('action::search'), utils.get_name('no_results'))
        return
    elif len(results) == 1:
        view_func(master, results[0])
        return

    def search_show():
        common.destroy_all_children(result_frame)
        btn.config(text='')
        f = form_cls(result_frame, None, lambda d: None)
        f.set_data({str(i): dns for i, dns in enumerate(results)})

    def view_wrap(_master, dns):
        common.destroy_all_children(result_frame)
        btn.config(text=utils.get_name('back_to_results'), command=search_show)
        return view_func(result_frame, dns)

    all_widgets = {str(i): (W.LINK, view_wrap, {'wraplength': WRAPLENGTH * 2})
                   for i in range(len(results))}
    form_cls = type('ConcreteSRForm', (SearchResultForm,), {'all_widgets': all_widgets})
    common.destroy_all_children(master)
    header = tk.Frame(master)
    header.pack()
    tk.Label(
        header,
        text=utils.get_name('{}_results', len(results)),
        wraplength=WRAPLENGTH,
    ).pack(side=tk.LEFT)
    btn = tk.Button(header, wraplength=WRAPLENGTH)
    btn.pack(side=tk.LEFT)
    result_frame = tk.Frame(master)
    result_frame.pack()
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
    common.destroy_all_children(master)
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
        (NSForm,),
        {'all_widgets': {'id': (W.OPTIONS_FROM_SEARCH, ans.ans, {})}},
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
        cur_login = core.Member.view_ns(
            main.app.current_login.name, login_context=core.internal_priv_lc).string
        main.app.header.set_info_text(utils.get_name('logged_in_as_{}', cur_login))
        main.app.header.set_login_text(utils.get_name('action::logout'))
    else:
        main.app.current_login = core.guest_lc
        main.app.header.set_info_text(utils.get_name('not_logged_in'))
        main.app.header.set_login_text(utils.get_name('action::login'))


def display_lua_data(data):
    """provide a callback for lua's display"""
    popup = tk.Toplevel(main.app.root)
    popup.transient(main.app.root)
    popup.grab_set()
    outer_frame = tk.Frame(popup)
    outer_frame.pack()
    size = config.gui2.widget_size.popup
    frame = tk.Frame(outer_frame, **size.mapping)
    frame.propagate(False)
    frame.grid(row=0, column=0)
    # This isn't quite right because the x-scrollbar (the button is outside the frame)
    # should also be considered, but it's probably good enough
    view_height = size.height // ttk.Style().configure('Treeview', 'rowheight')
    view = ttk.Treeview(frame, height=view_height)
    width, height = add_lua_data_entries(view, '', data)
    view.column('#0', width=width)
    if height > view['height']:
        sb = tk.Scrollbar(outer_frame, command=view.yview, orient=tk.VERTICAL)
        sb.grid(row=0, column=1, sticky=tk.NS)
        view['yscrollcommand'] = sb.set
    if width > config.gui2.widget_size.popup.width:
        sb = tk.Scrollbar(outer_frame, command=view.xview, orient=tk.HORIZONTAL)
        sb.grid(row=1, column=0, sticky=tk.EW)
        view['xscrollcommand'] = sb.set
    view.pack(expand=True, fill=tk.BOTH)
    tk.Button(popup, command=popup.destroy, text='OK').pack()


def add_lua_data_entries(view, parent, data, width=0, height=0, indent=1):
    """add entries to the Treeview and return (max width, total height)"""
    if isinstance(data, Sequence) and not isinstance(data, str):
        data = ((d, ()) if isinstance(d, str) else (i, d) for i, d in enumerate(data, 1))
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
        'bool': W.CHECKBOX,
        'str': NonEmptyEntry,
    }

    def get_name(internal):
        try:
            return name_data[internal]
        except KeyError:
            # only happens on errors
            return utils.get_name('form::' + internal)

    name_data = {'submit': utils.get_name('form::submit')}
    cls_body = {'get_name': staticmethod(get_name), 'all_widgets': {}}
    for k, name, t, *x in data_spec:
        choices = [c if isinstance(c, str) else (c['id'], c.string) for cs in x for c in cs]
        if t == 'choice':
            w = (W.DROPDOWN_CHOICES, choices, {'default': None})
        elif t == 'multichoices':
            w = (W.MULTI_CHOICE_POPUP, choices, {})
        else:
            w = type_widget_map[t]
        cls_body['all_widgets'][k] = w
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
    try:
        form = form_cls(main.app.center, None, cb)
    except core.BuchSchlossBaseError as e:
        tk_msg.showerror(e.title, e.message)
        main.app.reset()
    else:
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


# Form definitions


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
            partial(view_data, 'person'),
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
            partial(view_data, 'book'),
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


class MemberChangePasswordForm(AuthedForm):
    all_widgets = {
        'member': (
            W.FALLBACK_OFS,
            core.Member,
            {'fb_default': lambda: getattr(main.app.current_login, 'name', None)},
        ),
        'current_password': PasswordEntry,
        'new_password': W.CONFIRMED_PASSWORD_INPUT,
    }


class LoginForm(NSForm):
    all_widgets = {
        'name': NonEmptyREntry,
        'password': PasswordEntry,
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


class BorrowRestituteForm(BaseForm):
    all_widgets = {
        'book': (W.OPTIONS_FROM_SEARCH, core.Book,
                 {'condition': ('borrow.is_back', 'eq', False)}),
    }


class BorrowExtendForm(BaseForm):
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
