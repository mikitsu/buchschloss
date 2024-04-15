"""translate GUI actions to core-provided functions"""

import collections.abc
import logging
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
from .. import aforms
from ..aforms import Widget as W, FormTag
from ..aforms.defs import AuthedForm, PasswordEntry, NonEmptyREntry, IntEntry, NonEmptyEntry
from .formlib import Form as LibForm, ScrolledForm
from . import widgets
from .widgets import WRAPLENGTH


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

    def get_data(self):
        """handle SEARCH and EDIT

        for SEARCH tags, ignore empty data
        for EDIT tags, move the ID widget value to `*args`
        """
        if self.tag is FormTag.SEARCH:
            return {k: v
                    for k, v in super().get_data().items()
                    if v or isinstance(v, bool)}
        else:
            data = super().get_data()
            if self.tag is FormTag.EDIT:
                data['*args'] = (data.pop(self.id_name),)
            return data

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

    def get_submit_widget(self):
        """Don't show a submit button when used with FormTag.VIEW"""
        if self.tag is FormTag.VIEW:
            return None
        else:
            return super().get_submit_widget()


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
    form_cls = form_classes.get(
        f'{name.capitalize()}{func.title().replace("_", "")}Form',
        form_classes[name.capitalize() + 'Form']
    )
    tag = FormTag.__members__.get(func.upper())
    if func == 'view':
        return partial(view_action, master, ans)
    if func == 'search':
        middle_callback = partial(search_callback, master, name, ans)
        callback = partial(callback_adapter, middle_callback, False)
    else:
        callback = partial(callback_adapter, getattr(ans, func), True)
    return partial(form_cls, master, tag, callback)


def show_results(master: tk.Widget,
                 results: Sequence,
                 view_key: str,
                 ans: common.NSWithLogin,
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
        view_data(view_key, master, ans.view_ns(results[0]['id']))
        return

    def search_show():
        common.destroy_all_children(result_frame)
        btn.config(text='')
        f = form_cls(result_frame, None, lambda d: None)
        f.set_data({str(i): dns for i, dns in enumerate(results)})

    def view_wrap(_view_key, _master, dns):
        assert _view_key == view_key and _master is result_frame, (view_key, _view_key, _master, result_frame)
        common.destroy_all_children(result_frame)
        btn.config(text=utils.get_name('back_to_results'), command=search_show)
        return view_data(view_key, result_frame, ans.view_ns(dns['id']))

    all_widgets = {str(i): (W.LINK, view_key, {'wraplength': WRAPLENGTH * 2, 'view_func': view_wrap})
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
                    view_key: str,
                    ans: common.NSWithLogin,
                    search_mode: str,
                    exact_match: bool,
                    **kwargs,
                    ):
    """Provide a search-specific callback. Intended for use with ``functools.partial``.

    This callback displays the search results with :func:`.show_results`.
    These arguments are meant to be given beforehand:
    :param master: is passed to :func:`.show_results`
    :param view_key: is passed to :func:`.show_results`
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

    show_results(master, tuple(ans.search(q)), view_key, ans)


def view_data(name: str, master: tk.Widget, dns: core.DataNamespace):
    """Display data. Useful with ``functools.partial``.

    :param name: is a :func:`.make_action`-compatible name
    :param master: is the master widget to display data in
    :param dns: is a DataNamespace of the object to display
    """
    common.destroy_all_children(master)
    form_cls: Type[BaseForm] = form_classes[name.capitalize() + 'Form']
    form = form_cls(master, FormTag.VIEW, lambda **kw: None)
    try:
        form.set_data(dns)
    except core.BuchSchlossBaseError as e:
        tk_msg.showerror(e.title, e.message)
    except Exception:
        tk_msg.showerror(None, utils.get_name('unexpected_error'))
        raise


widgets.LinkWidget.view_func = view_data


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

form_classes = aforms.instantiate(BaseForm)
