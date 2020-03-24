"""GUIv2 for buchschloss"""

import tkinter.messagebox as tk_msg
import tkinter.font as tk_font
import tkinter as tk
from functools import partial
import queue
import threading
import time
import sys
import typing as T

from ..misc import tkstuff as mtk

try:
    from collections.abc import Mapping
except ImportError:
    Mapping = dict

from .. import core
from .. import utils
from .. import config
from . import forms
from . import widgets
from . import actions
from .actions import generic_formbased_action, ShowInfoNS, show_BSE


class NSWithLogin:
    """Wrap around an ActionNamespace providing the current login"""
    def __init__(self, ans: T.Type[core.ActionNamespace]):
        self.ans = ans

    def __getattr__(self, item):
        val = getattr(self.ans, item)
        if callable(val):
            return lambda *a, **kw: val(*a, login_context=app.current_login, **kw)
        else:
            return val


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
                horizontal=4 + (len(self.subactions) < 6)).pack()
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
        .current_login: a core.LoginContext instance
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.protocol('WM_CLOSE_WINDOW', self.onexit)
        self.root.attributes('-fullscreen', True)
        self.root.title('Buchschloss')
        font_conf = {'family': config.gui2.font.family, 'size': config.gui2.font.size}
        for font_name in ('Default', 'Text', 'Menu'):
            tk_font.nametofont(font_name.join(('Tk', 'Font'))).config(**font_conf)
        if not config.debug:
            sys.stderr = core.DummyErrorFile()
        self.current_login = core.guest_lc
        self.queue = queue.Queue()
        self.on_next_reset = []
        self.greeter = tk.Label(self.root,
                                text=config.gui2.intro.text,
                                font=config.gui2.intro.font)
        self.greeter.pack(fill=tk.BOTH)
        self.center = tk.Frame(self.root)
        self.header = widgets.Header(
            self.root,
            {'text': utils.get_name('actions::login'), 'command': actions.login},
            utils.get_name('not_logged_in'),
            {'text': utils.get_name('actions::abort'), 'command': self.reset},
            {'text': utils.get_name('actions::exit_app'), 'command': self.onexit}
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
        for cmd in self.on_next_reset:
            cmd()
        self.on_next_reset = []
        self.clear_center()
        self.display_start()

    @staticmethod
    def display_start():
        """initial view"""
        action_tree()

    def clear_center(self):
        """clear the center frame"""
        for w in self.center.children.copy().values():
            w.destroy()

    def onexit(self):
        """execute when the user exits the application"""
        if tk_msg.askokcancel(utils.get_name('actions::exit_app'),
                              utils.get_name('interactive_question::really_exit_app')):
            if (isinstance(sys.stderr, core.DummyErrorFile)
                    and sys.stderr.error_happened
                    and tk_msg.askokcancel(
                        None, utils.get_name('interactive_question::send_error_report'))):
                try:
                    utils.send_email(utils.get_name('error_in_buchschloss'),
                                     '\n\n\n'.join(sys.stderr.error_texts))
                except utils.requests.RequestException as e:
                    tk_msg.showerror(None, '\n'.join((
                        utils.get_name('error::error_while_sending_error_msg'), str(e))))
            self.root.destroy()
            sys.exit()

    def my_event_handler(self):  # TODO: move this to a proper scheduler
        """execute events outside of the tkinter event loop"""

        # in theory, I shouldn't need this, but misc.ScrollableWidget
        # doesn't work without calling .set_scrollregion(),
        # which in turn can't be done from inside a tkinter callback
        while True:
            event = self.queue.get()
            time.sleep(0.35)
            event()


def late_hook(late, warn):
    """Add an action to view late books. This is a late handler for utils"""
    actions.view_late = partial(actions.view_late, late, warn)


def new_book_autofill(form):
    """automatically fill some information on a book"""

    def filler(event=None):
        try:
            if str(form) not in str(app.root.focus_get()):
                # going somewhere else
                return
        except KeyError as e:
            if str(e) == "'__tk__messagebox'":
                return
            else:
                raise
        valid, isbn = isbn_field.validate()
        if not valid:
            tk_msg.showerror(message=isbn)
            isbn_field.focus()
            return
        if not tk_msg.askyesno(utils.get_name('actions::new__Book'),
                               utils.get_name('interactive_question::isbn_autofill')):
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


app = App()

FORMS = {
    'book': forms.BookForm,
    'person': forms.PersonForm,
    'library': forms.LibraryForm,
    'group': forms.GroupForm,
    'activate_group': forms.GroupActivationForm,
    'member': forms.MemberForm,
    'change_password': forms.ChangePasswordForm,
}
wrapped_action_ns = {
    k: NSWithLogin(getattr(core, k.capitalize()))
    for k in ('book', 'person', 'group', 'library', 'borrow', 'member')
}

action_tree = ActionTree.from_map({
    'new': {  # TODO: add an AddDict to misc to be able to insert the stuff here
        k: generic_formbased_action('new', FORMS[k], wrapped_action_ns[k].new)
        for k in ('book', 'person', 'library', 'group', 'member')
        # book here to keep it 1st with insertion ordered dicts
    },
    'view': {
        'book': ShowInfoNS.book,
        'person': ShowInfoNS.person,
    },
    'edit': {k: generic_formbased_action('edit', FORMS[k], wrapped_action_ns[k].edit,
                                         fill_data=wrapped_action_ns[k].view_str)
             for k in ('book', 'person', 'member')
    },  # noqa
    'search': {k: actions.search(f, wrapped_action_ns[k].search, getattr(ShowInfoNS, k))
               for f, k in (
        (forms.BookForm, 'book'),
        (forms.PersonForm, 'person'),
        (forms.BorrowSearchForm, 'borrow'),
    )
    },
    'borrow': actions.borrow_restitute(
        forms.BorrowForm, wrapped_action_ns['borrow'].new),
    'restitute': actions.borrow_restitute(
        forms.RestituteForm, wrapped_action_ns['borrow'].restitute),
})
action_tree.new.book = generic_formbased_action(
    'new', FORMS['book'], actions.new_book, post_init=new_book_autofill)
action_tree.edit.change_password = generic_formbased_action(
    'edit', FORMS['change_password'], wrapped_action_ns['member'].change_password)
action_tree.edit.activate_group = generic_formbased_action(
    'edit', FORMS['activate_group'], wrapped_action_ns['group'].activate)
action_tree.edit.library = generic_formbased_action(
    'edit', FORMS['library'], wrapped_action_ns['library'].edit)
action_tree.edit.group = generic_formbased_action(
    'edit', FORMS['group'], wrapped_action_ns['group'].edit)
