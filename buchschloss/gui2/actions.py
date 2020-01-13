"""translate GUI actions to core-provided functions"""

import collections
import tkinter as tk
import tkinter.messagebox as tk_msg
from functools import partial
import logging
import typing as T

from ..misc import tkstuff as mtk
from ..misc.tkstuff import dialogs as mtkd
from ..misc import validation as mval
from . import main
from . import forms
from . import widgets
from .. import core
from .. import utils
from .. import config


def show_BSE(e):
    tk_msg.showerror(e.title, e.message)


# noinspection PyDefaultArgument
def generic_formbased_action(form_type, form_cls, callback,
                             form_options={}, fill_data=None,
                             post_init=lambda f: None,
                             do_reset=True):
    """perform a generic action
        Arguments:
            form_type: 'new', 'edit' or 'search': used for the form group  TODO: make this an enum
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


def show_results(results, view_func, master=None):
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


def search(form_cls, namespace: core.ActionNamespace, view_func):
    """wrapper for generic_formbased_action for search actions

    Arguments:
        - form_cls: the misc.tkstuff.forms.Form subclass
        - namespace: the core namespace in which the search and view functions are
    """
    def search_callback(*, search_mode, exact_match, **kwargs):
        q = ()
        for k, val_seq in kwargs.items():
            if isinstance(val_seq, str) or not isinstance(val_seq, collections.abc.Sequence):
                val_seq = [val_seq]
            for v in val_seq:
                if exact_match or not isinstance(v, str):
                    q = ((k, 'eq', v), search_mode, q)
                else:
                    q = ((k, 'contains', v), search_mode, q)

        results = namespace.search(q)
        print(q, kwargs)
        show_results(results, view_func)

    return generic_formbased_action('search', form_cls, search_callback, do_reset=False)


def func_from_static(static: staticmethod):
    # removes scary warnings when using functions inside a class body
    return static.__func__


class ShowInfoNS:
    """namespace for information viewing"""
    # noinspection PyDefaultArgument,PyNestedDecorators
    @func_from_static
    @staticmethod
    def _show_info_action(namespace: T.Type[core.ActionNamespace],
                          special_keys={}, id_get_title='ID',
                          id_get_text='ID:', id_type=int):
        """prepare a fcuntion displaying information

        Arguments:
            - namespace: the namespace with the viewing function
            - special_keys: a mapping form keys in the returned data to a function
                taking the value mapped by the key and returning a value to pass
                to widgets.InfoWidget. Optionally, a different name for the field
                may be returned as first element in a sequence, the display value
                being second
            TODO -- move to a form-based question
            - id_get_title: the title of the popup window asking for the ID
            - id_get_text: the text of the window askinf for the ID
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
                            'must_be_{}'.format(id_type.__name__))}))
                    id_ = mtkd.WidgetDialog.ask(
                        main.app.root, mtk.ValidatedWidget.new_cls(tk.Entry, validator),
                        title=id_get_title, text=id_get_text)
                except mtkd.UserExitedDialog:
                    main.action_tree.view()
                    return

            try:
                data = namespace.view_str(id_)
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
        core.Book,
        {'borrowed_by': lambda d: (
            utils.get_name('borrowed_by'), (widgets.Button, {
                'text': utils.break_string(str(d['borrowed_by']),
                                           config.gui2.info_widget.item_length),
                'command': (partial(ShowInfoNS.person, d['borrowed_by_id'])
                            if d['borrowed_by_id'] is not None else None)
            }))
         },
        utils.get_name('view__book'),
        utils.get_name('book_id')
    )
    person = _show_info_action(
        core.Person,
        {'borrows': lambda d: (
            [(widgets.Button, {
                'text': utils.break_string(t, config.gui2.info_widget.item_length),
                'command': partial(ShowInfoNS.book, i)})
             for t, i in zip(d['borrows'], d['borrow_book_ids'])],
            )
         },
        utils.get_name('view__person'),
        utils.get_name('id')
    )
    borrow = _show_info_action(
        core.Borrow,
        {'person': lambda d: (
            (widgets.Button, {
                'text': utils.break_string(d['person'],
                                           config.gui2.info_widget.item_length),
                'command': partial(ShowInfoNS.person, d['person_id'])
            }),),
         'book': lambda d: (
             (widgets.Button, {
                 'text': utils.break_string(d['book'],
                                            config.gui2.info_widget.item_length),
                 'command': partial(ShowInfoNS.book, d['book_id'])
             }),),
         'is_back': lambda d: (
             (widgets.Label, {
                 'text': utils.get_name(str(d['is_back']))
             }),),
         },
    )
    to_destroy = None


def login():
    """log in"""
    if isinstance(core.current_login, core.Dummy):
        try:
            data = mtkd.FormDialog.ask(main.app.root, forms.LoginForm)
        except mtkd.UserExitedDialog:
            return
        try:
            core.login(**data)
        except core.BuchSchlossBaseError as e:
            tk_msg.showerror(e.title, e.message)
            return
        main.app.header.set_info_text(utils.get_name('logged_in_as_{}'
                                                     ).format(core.current_login))
        main.app.header.set_login_text(utils.get_name('logout'))
    else:
        core.logout()
        main.app.header.set_info_text(utils.get_name('logged_out'))
        main.app.header.set_login_text(utils.get_name('login'))


def view_late(late, warn):
    """show late books"""
    show_results(warn+late, ShowInfoNS.borrow)


def borrow_restitute(form_cls, callback):
    """function for borrow and restitute actions"""
    def add_btn(form):
        try:
            pw = [(widgets.Button, {'text': core.Person.view_repr(p),
                                    'command': partial(form.inject_submit, person=p)})
                  for p in core.misc_data.latest_borrowers]
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
    tk_msg.showinfo(utils.get_name('new_book'), utils.get_name('new_book_id_is_%s')
                    % core.Book.new(**kwargs))
