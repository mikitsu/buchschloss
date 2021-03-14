"""translate GUI actions to core-provided functions"""

import collections
import itertools
import tkinter as tk
import tkinter.messagebox as tk_msg
from functools import partial
import typing as T

from ..misc import tkstuff as mtk
from ..misc.tkstuff import dialogs as mtkd
from ..misc.tkstuff import forms as mtkf
from . import main
from . import forms
from . import widgets
from . import common
from .. import core
from .. import config
from .. import utils


# noinspection PyDefaultArgument
def generic_formbased_action(form_type, form_cls, callback,
                             form_options={}, fill_data=None,
                             post_init=lambda f: None,
                             do_reset=True):
    # TODO: make form_type an enum
    """perform a generic action
        Arguments:
            form_type: 'new', 'edit' or 'search': used for the form group
            form_cls: the form class (subclass of misc.tkstuff.forms.Form)
            callback: the function to call on form submit with form data as keyword arguments
            form_options: optional dict of additional options for the form
            fill_data: optional callable taking the input of the first form field
                and returning a dict of data to fill into the form
            post_init: called after creation and placement of the form
                with the form instance as argument
            do_reset: boolean indicating whether to call app.reset after form submission"""
    form_options_ = {
        k: {'groups': v} for k, v in {
            'new': [forms.ElementGroup.NEW],
            'edit': [forms.ElementGroup.EDIT],
            'search': [forms.ElementGroup.SEARCH],
            None: [],
        }.items()
    }
    form_options_['edit']['default_content'] = {}
    form_options_ = form_options_.get(form_type, {})
    form_options_.update(form_options)

    def action(event=None):
        def onsubmit(data):
            if fill_data is not None:
                valid, id_ = id_field.validate()
                if valid:
                    mod = [id_]
                    del data[id_name]
                else:
                    tk_msg.showerror()
                    return
            else:
                mod = ()
            try:
                r = callback(*mod, **data)
            except core.BuchSchlossBaseError as e:
                tk_msg.showerror(e.title, e.message)
            except Exception:
                tk_msg.showerror(None, utils.get_name('unexpected_error'))
                raise
            else:
                if r and isinstance(r, set):
                    tk_msg.showerror(None, utils.get_name('errors_{}').format('\n'.join(r)))
                else:
                    form.destroy()
                    if do_reset:
                        main.app.reset()

        form = form_cls(main.app.center, onsubmit=onsubmit, **form_options_)
        if fill_data is not None:
            id_field = form.widgets[0]
            id_name = {id(v): k for k, v in form.widget_dict.items()}[id(id_field)]

            def fill_fields(event=None):
                with common.ignore_missing_messagebox():
                    if str(form) not in str(main.app.root.focus_get()):
                        return  # going somewhere else
                valid, id_ = id_field.validate()
                if not valid:
                    tk_msg.showerror(None, id_)
                    id_field.focus()
                    return
                try:
                    data = fill_data(id_)
                except core.BuchSchlossBaseError as e:
                    tk_msg.showerror(e.title, e.message)
                    id_field.focus()
                else:
                    for k, w in form.widget_dict.items():
                        v = getattr(data, k, None)
                        if v is not None:
                            mtk.get_setter(w)(v)
            id_field.bind('<FocusOut>', fill_fields)
        form.widgets[0].focus()
        form.pack()
        post_init(form)
    return action


def show_results(results: T.Iterable, view_func: T.Callable[[T.Any], dict], master=None):
    """show search results as buttons taking the user to the appropriate view

        Arguments:
            - results: an iterable of objects as those returned by core.*.search
            - view_func: the function to display information to the user
            - master: the master widget, app.center by default
    """
    if master is None:
        master = main.app.center

    def search_hide():
        rw.pack_forget()
        show_btn = widgets.Button(search_frame, text=utils.get_name('back_to_results'))
        show_btn.config(command=partial(search_show, show_btn))
        show_btn.pack()

    def search_show(btn):
        btn.destroy()
        ShowInfo.to_destroy.container.destroy()
        ShowInfo.to_destroy = None
        rw.pack()

    def view_wrap(*args, **kwargs):
        search_hide()
        return view_func(*args, **kwargs)

    search_frame = tk.Frame(master)
    search_frame.pack()
    rw = widgets.SearchResultWidget(search_frame, tuple(results), view_wrap)
    rw.pack()


def search(form_cls: T.Type[forms.BaseForm],
           search_func: T.Callable[[T.Any], T.Iterable],
           view_func: T.Callable[[T.Any], dict]
           ) -> T.Callable[[T.Optional[tk.Event]], None]:
    """wrapper for generic_formbased_action for search actions

    Arguments:
        - form_cls: the misc.tkstuff.forms.Form subclass
        - search_func: the function for searching
        - view_func: the function for viewing individual results
    """
    def search_callback(*, search_mode, exact_match, **kwargs):
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

        results = search_func(q)
        show_results(results, view_func)

    return generic_formbased_action('search', form_cls, search_callback, do_reset=False)


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
                           for k in ('Library', 'Group', 'Member', 'Script')})


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


def new_book(**kwargs):
    tk_msg.showinfo(utils.get_name('Book'),
                    utils.get_name('Book::new_id_{}')
                    .format(core.Book.new(login_context=main.app.current_login,
                                          **kwargs)))


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
