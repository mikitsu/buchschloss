"""GUIv2 for buchschloss"""

import tkinter.messagebox as tk_msg
import tkinter.font as tk_font
import tkinter as tk
from functools import partial
import queue
import threading
import logging
import time
import sys
import typing as T

import misc.validation as mval
import misc.tkstuff as mtk
import misc.tkstuff.dialogs as mtkd
try:
    from collections.abc import Mapping
except ImportError:
    Mapping = dict


from .. import core
from .. import utils
from .. import config
from . import forms
from . import widgets


def func_from_static(static: staticmethod):
    # removes scary warnings when using functions inside a class body
    return static.__func__


def show_BSE(e):
    tk_msg.showerror(e.title, e.message)


class ActionTree:
    def __getattr__(self, name):
        if name not in self.subactions:
            setattr(self, name, None)
        return self.subactions[name]

    def __setattr__(self, name, value):
        if isinstance(value, __class__):
            self.subactions[name] = value
        else:
            self.subactions[name] = type(self)(value)

    def __init__(self, action=None):
        super().__setattr__('subactions', {})
        super().__setattr__('action', action)
        super().__setattr__('__name__', repr(self))

    def __call__(self, *args, **kwargs):
        def call_wrapper_for_unknown_reasons(func):
            # this also works with a class defining __call__,
            # it might be a problem with ?? the NAME ??
            return lambda *a, **kw: func(*a, **kw)

        CWFUR = call_wrapper_for_unknown_reasons
        app.clear_center()
        if self.action is None:
            widgets.ActionChoiceWidget(
                app.center, ((k, CWFUR(v)) for k, v in self.subactions.items()),
                horizontal=4+(len(self.subactions) < 6)).pack()
        else:
            return self.action(*args, **kwargs)

    @classmethod
    def from_map(cls, mapping):
        self = cls(mapping.pop('**here**', None))
        for name, val in mapping.items():
            if isinstance(val, Mapping):
                val = cls.from_map(val)
            setattr(self, name, val)
        return self


class App:
    """The main application

        Attributes:
        .header: the top bar including login, reset and exit
        .center: the main part
        .queue: actions to be executed separately from the tk event loop
        .root: the tk.Tk instance
    """
    def __init__(self):
        self.root = tk.Tk()
        self.root.protocol('WM_CLOSE_WINDOW', self.onexit)
        self.root.attributes('-fullscreen', True)
        self.root.title('Buchschloss')
        tk_font.nametofont('TkDefaultFont').config(**config.gui_font)
        tk_font.nametofont('TkTextFont').config(**config.gui_font)
        if not getattr(config, 'DEBUG', False):
            sys.stderr = core.DummyErrorFile()
        else:
            print('ATTENTION -- sys.stderr not redirected', file=sys.stderr)
        self.queue = queue.Queue()
        self.greeter = tk.Label(self.root, **config.intro)
        self.greeter.pack(fill=tk.BOTH)
        self.center = tk.Frame(self.root)
        self.header = widgets.Header(
            self.root,
            {'text': utils.get_name('login'), 'command': action_login},
            utils.get_name('not_logged_in'),
            {'text': utils.get_name('abort'), 'command': self.reset},
            {'text': utils.get_name('exit_app'), 'command': self.onexit}
        )

    def launch(self):
        """remove greeting screen in 3 seconds and start the min loop"""
        self.root.after(3000, self.start)
        self.root.mainloop()

    def start(self):
        """remove the greeting screen and show default screen"""
        self.greeter.destroy()
        self.header.pack()
        self.center.pack()
        self.display_start()
        threading.Thread(target=self.my_event_handler, daemon=True).start()

    def reset(self):
        """reset to initial view"""
        self.clear_center()
        self.display_start()

    @staticmethod
    def display_start():
        """initial view"""
        actions()

    def clear_center(self):
        """clear the center frame"""
        for w in self.center.children.copy().values():
            w.destroy()

    def onexit(self):
        """execute when the user exits the application"""
        if tk_msg.askokcancel(utils.get_name('exit_app'),
                              utils.get_name('really_exit_app')):
            if sys.stderr.error_happened and tk_msg.askokcancel(
                    None, utils.get_name('send_error_report')):
                try:
                    utils.send_mailgun('Error in Schuelerbuecherei', '\n\n\n'.join(sys.stderr.error_texts))
                except utils.requests.RequestException as e:
                    tk_msg.showerror(None, '\n'.join((utils.get_name('error_while_sending_error_msg'), str(e))))
            self.root.destroy()
            sys.exit()

    def my_event_handler(self):
        """execute events outside of the tkinter event loop TODO: move this to a proper scheduler"""
        # in theory, I shouldn't need this, but misc.ScrollableWidget
        # doesn't work without calling .set_scrollregion(),
        # which in turn can't be done from inside a tkinter callback
        while True:
            event = self.queue.get()
            time.sleep(0.35)
            event()
app = App()


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
                and returning a dict of datat to fill into the form
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
                        app.reset()

        form = form_cls(app.center, onsubmit=onsubmit, **form_options_)
        if fill_data is not None:
            id_field = form.widgets[0]
            id_name = {id(v): k for k, v in form.widget_dict.items()}[id(id_field)]

            def fill_fields(event=None):
                if str(form) not in str(app.root.focus_get()):
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
            - view_func: the function to call for wiewing an object
            - master: the master widget, app.center by default
    """
    if master is None:
        master = app.center

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
        except AttributeError:
            # don't crash everythng if I stop using ScrollableWidget
            sys.stderr.write('WARN -- in show_results.<locals>.search_show\n')
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
    app.queue.put(rw.set_scrollregion)
    app.root.bind('<q>', lambda e: rw.set_scrollregion())


def search_action(form_cls, namespace: core.ActionNamespace):
    """wrapper for generic_formbased_action for search actions

    Arguments:
        - form_cls: the misc.tkstuff.forms.Form subclass
        - namespace: the core namespace in which the search and view functions are
    """
    def search_callback(*, search_mode, exact_match, **kwargs):
        q = ()
        for k, v in kwargs.items():
            if exact_match or isinstance(v, str):
                q = ((k, 'eq', v), search_mode, q)
            else:
                q = ((k, 'contains', v), search_mode, q)

        results = namespace.search(q)
        show_results(results, namespace.view_str)

    return generic_formbased_action('search', form_cls, search_callback, do_reset=False)


def late_hook(late, warn):
    """Add an action to view late books. This is a late handler for utils"""
    actions.view_late = partial(view_late, late, warn)


def view_late(late, warn):
    """show late books"""
    show_results(warn+late, ShowInfoNS.borrow)


def borrow_restitute(form_cls, callback):
    """function for borrow and restitute actions"""
    def add_btn(form):
        pw = [(widgets.Button, {'text': core.Person.view_repr(p),
                                'command': partial(form.inject_submit, person=p)})
              for p in core.misc_data.latest_borrowers]
        widgets.mtk.ContainingWidget(app.center, *pw, horizontal=2).pack()

    def callback_wrapper(book=None, person=None, borrow_time=None):
        if borrow_time is None:
            return callback(book, person)
        else:
            return callback(book, person, borrow_time)

    return generic_formbased_action(None, form_cls, callback_wrapper, post_init=add_btn)


def new_book_autofill(form):
    """automatically fill some information on a book"""
    def filler(event=None):
        if str(form) not in str(app.root.focus_get()):
            # going somewhere else
            return
        valid, isbn = isbn_field.validate()
        if not valid:
            tk_msg.showerror(message=isbn)
            isbn_field.focus()
            return
        if not tk_msg.askyesno(utils.get_name('create_book'), utils.get_name('ask_isbn_autofill')):
            return
        try:
            data = utils.get_book_data(isbn)
        except core.BuchSchlossBaseError as e:
            show_BSE(e)
        else:
            for k, v in data.items():
                mtk.get_setter(form.widget_dict[k])(v)

    isbn_field = form.widget_dict['isbn']
    isbn_field.bind('<FocusOut>', filler)


def activate_group_wrapper(name, src, dest):
    """allow activation of multiple groups"""
    e = set()
    for n in name.split(';'):
        e |= core.Group.activate(n, src, dest)
    return e


class ShowInfoNS:
    """namespace for information viewing"""
    # noinspection PyDefaultArgument,PyNestedDecorators
    @func_from_static
    @staticmethod
    def show_info_action(namespace: T.Type[core.ActionNamespace],
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
                        app.root, mtk.ValidatedWidget.new_cls(tk.Entry, validator),
                        title=id_get_title, text=id_get_text)
                except mtkd.UserExitedDialog:
                    actions.view()
                    return

            try:
                data = namespace.view_str(id_)
            except core.BuchSchlossBaseError as e:
                show_BSE(e)
                app.reset()
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
            iw = widgets.InfoWidget(app.center, pass_widgets)
            iw.pack()
            app.queue.put(iw.set_scrollregion)
            app.root.bind('<q>', lambda e: iw.set_scrollregion())
            ShowInfoNS.to_destroy = iw

        return show_info

    book = show_info_action(
        core.Book,
        {'borrowed_by': lambda d: (
            utils.get_name('borrowed_by'), (widgets.Button, {
                'text': utils.break_string(str(d['borrowed_by']), config.INFO_LENGTH),
                'command': (partial(ShowInfoNS.person, d['borrowed_by_id'])
                            if d['borrowed_by_id'] is not None else None)
            }))
         },
        utils.get_name('view__book'),
        utils.get_name('book_id')
    )
    person = show_info_action(
        core.Person,
        {'borrows': lambda d: (
            [(widgets.Button, {
                'text': utils.break_string(t, config.INFO_LENGTH),
                'command': partial(ShowInfoNS.book, i)})
             for t, i in zip(d['borrows'], d['borrow_book_ids'])],
            )
         },
        utils.get_name('view__person'),
        utils.get_name('id')
    )
    borrow = show_info_action(
        core.Borrow,
        {'person': lambda d: (
            (widgets.Button, {
                'text': utils.break_string(d['person'], config.INFO_LENGTH),
                'command': partial(ShowInfoNS.person, d['person_id'])
            }),),
         'book': lambda d: (
             (widgets.Button, {
                 'text': utils.break_string(d['book'], config.INFO_LENGTH),
                 'command': partial(ShowInfoNS.book, d['book_id'])
             }),),
         'is_back': lambda d: (
             (widgets.Label, {
                 'text': utils.get_name(str(d['is_back']))
             }),),
         },
    )
    to_destroy = None


FORMS = {
    'book': forms.BookForm,
    'person': forms.PersonForm,
    'library': forms.LibraryForm,
    'group': forms.GroupForm,
    'activate_group': forms.GroupActivationForm,
    'member': forms.MemberForm,
    'change_password': forms.ChangePasswordForm,
    'borrow_search': forms.BorrowSearchForm,
}

actions = ActionTree.from_map({
    'new': {k: generic_formbased_action('new', FORMS[k], *v[:-1], **v[-1]) for k, v in {
        # 'name': (<callback>, [<other posinional args>, ]<kwargs>)
        'book': (lambda *a, **kw: (tk_msg.showinfo(None, utils.get_name('new_book_id_is_{}')
                                                   .format(core.new_book(*a, **kw)))),
                 {'post_init': new_book_autofill}),
        'person': (core.new_person, {}),
        'library': (partial(core.new_library_group, what='library'), {}),
        'group': (partial(core.new_library_group, what='group'), {}),
        'member': (core.new_member, {}),
        }.items()
    },
    'view': {
        'book': ShowInfoNS.book,
        'person': ShowInfoNS.person,
    },
    'edit': {k: generic_formbased_action('edit', FORMS[k], *v) for k, v in {
        'book': (core.edit_book, {}, core.view_book),
        'person': (core.edit_person, {}, core.view_person),
        'library': (partial(core.edit_library_group, 'library'),),
        'group': (partial(core.edit_library_group, 'group'),),
        'activate_group': (activate_group_wrapper,),
        'member': (core.edit_member, {}, core.view_member),
        'change_password': (core.change_password, {}, lambda a: {}),
        }.items()
    },
    'search': {k: search_action(FORMS[k], *v) for k, v in {
        'book': (core.models.Book, ShowInfoNS.book),
        'person': (core.models.Person, ShowInfoNS.person),
        'borrow_search': (core.models.Borrow, ShowInfoNS.borrow)
        }.items()
    },
    'borrow': borrow_restitute(forms.BorrowForm, core.borrow),
    'restitute': borrow_restitute(forms.RestituteForm, core.restitute),
})

start = app.launch
utils.late_handlers.append(late_hook)
