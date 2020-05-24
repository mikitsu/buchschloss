"""translate GUI actions to core-provided functions"""

import collections
import itertools
import tkinter as tk
import tkinter.messagebox as tk_msg
from functools import partial
import logging
import typing as T

from ..misc import tkstuff as mtk
from ..misc.tkstuff import dialogs as mtkd
from ..misc.tkstuff import forms as mtkf
from ..misc import validation as mval
from . import main
from . import forms
from . import widgets
from .. import core
from .. import utils


def show_BSE(e):
    tk_msg.showerror(e.title, e.message)


class NSWithLogin:
    """Wrap around an ActionNamespace providing the current login"""
    def __init__(self, ans: T.Type[core.ActionNamespace]):
        self.ans = ans

    def __getattr__(self, item):
        val = getattr(self.ans, item)
        if callable(val):
            return lambda *a, **kw: val(*a, login_context=main.app.current_login, **kw)
        else:
            return val


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
            'search': [forms.ElementGroup.SEARCH]
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
                    for k, v in data.items():
                        if k in form.widget_dict:
                            mtk.get_setter(form.widget_dict[k])(v)
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
        try:
            # workaround because mtk.ScrollableWidget doesn't handle .destroy() yet
            ShowInfoNS.to_destroy.container.destroy()
        except AttributeError as e:
            # don't crash everything if I stop using ScrollableWidget
            logging.error(e)
            ShowInfoNS.to_destroy.destroy()
        ShowInfoNS.to_destroy = None
        rw.pack()

    def view_wrap(*args, **kwargs):
        search_hide()
        return view_func(*args, **kwargs)

    search_frame = tk.Frame(master)
    search_frame.pack()
    rw = widgets.SearchResultWidget(search_frame, results, view_wrap)
    rw.pack()
    main.app.queue.put(rw.set_scrollregion)
    q_binding = main.app.root.bind('<q>', lambda e: rw.set_scrollregion())
    main.app.on_next_reset.append(lambda: main.app.root.unbind('<q>', q_binding))


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


def func_from_static(static: staticmethod):
    # removes scary warnings when using functions inside a class body
    return static.__func__


class ShowInfoNS:
    """namespace for information viewing"""

    # noinspection PyNestedDecorators
    @func_from_static
    @staticmethod
    def _show_info_action(view_func: T.Callable[[T.Any], dict],
                          special_keys, id_get_title,
                          id_get_text, id_type=int):
        """prepare a function displaying information

        Arguments:
            - namespace: the namespace with the viewing function
            - special_keys: a mapping form keys in the returned data to a function
                taking the value mapped by the key and returning a value to pass
                to widgets.InfoWidget. Optionally, a different name for the field
                may be returned as first element in a sequence, the display value
                being second
            TODO -- move to a form-based question
            - id_get_title: the title of the popup window asking for the ID
            - id_get_text: the text of the window asking for the ID
            - id_type: the type of the ID
        """

        def show_info(id_=None):
            if ShowInfoNS.to_destroy is not None:
                try:
                    # workaround because mtk.ScrollableWidget doesn't handle .destroy() yet
                    ShowInfoNS.to_destroy.container.destroy()
                except AttributeError as e:
                    # don't crash everything if I stop using ScrollableWidget
                    logging.error(e)
                    ShowInfoNS.to_destroy.destroy()
            if id_ is None:
                try:
                    validator = mval.Validator((
                        id_type, {ValueError: utils.get_name(
                            'error::must_be_{}'.format(id_type.__name__))}))
                    id_ = mtkd.WidgetDialog.ask(
                        main.app.root, mtk.ValidatedWidget.new_cls(tk.Entry, validator),
                        title=id_get_title, text=id_get_text)
                except mtkd.UserExitedDialog:
                    main.action_tree.view()
                    return

            try:
                data = view_func(id_)
            except core.BuchSchlossBaseError as e:
                show_BSE(e)
                main.app.reset()
                return
            pass_widgets = {utils.get_name('info_regarding'): data['__str__']}
            for k, v in data.items():
                if k in special_keys:
                    *k_new, v = special_keys[k](data)
                    if k_new:
                        k = k_new[0]
                    else:
                        k = utils.get_name(k)
                    pass_widgets[k] = v
                elif '_id' not in k and k != '__str__':
                    pass_widgets[utils.get_name(k)] = str(v)
            iw = widgets.InfoWidget(main.app.center, pass_widgets)
            iw.pack()
            main.app.queue.put(iw.set_scrollregion)
            main.app.root.bind('<q>', lambda e: iw.set_scrollregion())
            ShowInfoNS.to_destroy = iw

        return show_info

    book = _show_info_action(
        NSWithLogin(core.Book).view_str,
        {'borrowed_by': lambda d: (
            utils.get_name('borrowed_by'), (widgets.Button, {
                'text': d['borrowed_by'],
                'command': (partial(ShowInfoNS.person, d['borrowed_by_id'])
                            if d['borrowed_by_id'] is not None else None)
            }))
         },
        utils.get_name('actions::view__Book'),
        utils.get_name('Book::id')
    )
    person = _show_info_action(
        NSWithLogin(core.Person).view_str,
        {'borrows': lambda d: (
            [(widgets.Button, {
                'text': t,
                'command': partial(ShowInfoNS.book, i)})
             for t, i in zip(d['borrows'], d['borrow_book_ids'])],
        )
        },
        utils.get_name('actions::view__Person'),
        utils.get_name('Person::id')
    )
    borrow = _show_info_action(
        NSWithLogin(core.Borrow).view_str,
        {'person': lambda d: (
            (widgets.Button, {
                'text': d['person'],
                'command': partial(ShowInfoNS.person, d['person_id'])
            }),),
         'book': lambda d: (
             (widgets.Button, {
                 'text': d['book'],
                 'command': partial(ShowInfoNS.book, d['book_id'])
             }),),
         'is_back': lambda d: (
             (widgets.Label, {
                 'text': utils.get_name(str(d['is_back']))
             }),),
         },
        'not used',
        'anyway',
    )
    to_destroy = None


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
        main.app.header.set_info_text(utils.get_name('logged_in_as_{}'
                                                     ).format(main.app.current_login))
        main.app.header.set_login_text(utils.get_name('actions::logout'))
    else:
        main.app.current_login = core.guest_lc
        main.app.header.set_info_text(utils.get_name('logged_out'))
        main.app.header.set_login_text(utils.get_name('actions::login'))


def view_late(late, warn):
    """show late books"""
    show_results(warn + late, ShowInfoNS.borrow)


def borrow_restitute(form_cls, callback):
    """function for borrow and restitute actions"""
    def add_btn(form):
        try:
            pw = [(widgets.Button, {
                'text': core.Person.view_repr(p, login_context=main.app.current_login),
                'command': partial(form.inject_submit, person=p)
            }) for p in core.misc_data.latest_borrowers]
            widgets.mtk.ContainingWidget(main.app.center, *pw, horizontal=2).pack()
        except core.BuchSchlossBaseError as e:
            show_BSE(e)

    return generic_formbased_action(None, form_cls, callback, post_init=add_btn)


def activate_group(name, src, dest):
    """allow activation of multiple groups"""
    e = set()
    for n in name.split(';'):
        e |= core.Group.activate(n, src, dest)
    return e


def new_book(**kwargs):
    tk_msg.showinfo(utils.get_name('actions::new__Book'),
                    utils.get_name('Book::new_id_{}')
                    .format(core.Book.new(login_context=main.app.current_login,
                                          **kwargs)))


def display_cli2_data(data):
    """provide a callback for cli2's display"""
    popup = tk.Toplevel(main.app.root)
    popup.transient()
    popup.grab_set()
    widget_cls, kwargs = get_cli2_data_widget(popup, data)
    # TODO: make scrolled?
    # this relies on strict LtR evaluation. If it breaks, just use two lines
    widget = widget_cls(popup, *kwargs.pop('*args', ()), **kwargs)
    widget.pack()
    tk.Button(popup, command=popup.destroy, text='OK').pack()


def get_cli2_data_widget(master, data):
    """recursively create a widget for cli' display callback"""
    if isinstance(data, dict):
        return (mtk.ContainingWidget,
                {'*args': itertools.chain(*(((tk.Label, {'text': k}),
                                            get_cli2_data_widget(master, v))
                                            for k, v in data.items())),
                 'horizontal': 2})
    elif isinstance(data, T.Sequence) and not isinstance(data, str):
        return (mtk.ContainingWidget,
                {'*args': map(partial(get_cli2_data_widget, master), data),
                 'direction': (tk.BOTTOM, tk.RIGHT)})
    else:
        return (tk.Label, {'text': data})


def handle_cli2_get_data(data_spec):
    """provide a callback for cli2's get_data"""
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
