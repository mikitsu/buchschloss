"""GUIv2 for buchschloss"""

import collections
import functools
import operator
import logging
import tkinter.messagebox as tk_msg
import tkinter.font as tk_font
import tkinter as tk
import types
from functools import partial
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
from ..config.main import DummyErrorFile
from . import forms
from . import widgets
from . import actions
from . import common
from .actions import generic_formbased_action, ShowInfo


class ActionTree(dict):
    def __call__(self):
        app.clear_center()
        # this can probably be done better
        width = config.gui2.action_width
        orphan_n = len(self) % width or float('inf')
        orphan_nm1 = len(self) % (width - 1 or width) or float('inf')
        if orphan_n < orphan_nm1:
            width -= 1
        widgets.ActionChoiceWidget(app.center, self.items(), horizontal=width).pack()

    @classmethod
    def from_nested(cls, mapping: T.Mapping):
        """auto-generate sub-ActionTrees"""
        r = {}
        for k, v in mapping.items():
            if isinstance(v, T.Mapping):
                action = cls.from_nested(v)
            else:
                def action(_f=v):
                    app.clear_center()
                    _f()
            r[k] = action
        return ActionTree(r)


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
        self.current_login = core.guest_lc
        self.on_next_reset = []
        self.greeter = tk.Label(self.root,
                                text=config.gui2.intro.text,
                                font=config.gui2.intro.font)
        self.greeter.pack(fill=tk.BOTH)
        self.center = tk.Frame(self.root)
        self.header = widgets.Header(
            self.root,
            {'text': utils.get_name('action::login'), 'command': actions.login},
            utils.get_name('not_logged_in'),
            {'text': utils.get_name('action::abort'), 'command': self.reset},
            {'text': utils.get_name('action::exit_app'), 'command': self.onexit}
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
        for script_spec in config.gui2.startup_scripts:
            utils.get_script_target(script_spec, login_context=core.internal_unpriv_lc)()

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
        if tk_msg.askokcancel(utils.get_name('action::exit_app'),
                              utils.get_name('interactive_question::really_exit_app')):
            if (isinstance(sys.stderr, DummyErrorFile)
                    and sys.stderr.error_happened
                    and tk_msg.askokcancel(
                        None, utils.get_name('interactive_question::send_error_report'))):
                try:
                    utils.send_email(utils.get_name('error_in_buchschloss'),
                                     '\n\n\n'.join(sys.stderr.error_texts))
                except Exception as e:
                    tk_msg.showerror(None, '\n'.join((
                        utils.get_name('error::error_while_sending_error_msg'), str(e))))
            self.root.destroy()
            sys.exit()


def new_book_autofill(form):
    """automatically fill some information on a book"""

    def filler(event=None):
        with common.ignore_missing_messagebox():
            if str(form) not in str(app.root.focus_get()):
                # going somewhere else
                return
        valid, isbn = isbn_field.validate()
        if not valid:
            tk_msg.showerror(message=isbn)
            isbn_field.focus()
            return
        if not tk_msg.askyesno(utils.get_name('book::isbn'),
                               utils.get_name('interactive_question::isbn_autofill')):
            return
        try:
            data = utils.get_book_data(isbn)
        except core.BuchSchlossBaseError as e:
            tk_msg.showerror(e.title, e.message)
        else:
            for k, v in data.items():
                mtk.get_setter(form.widget_dict[k])(v)

    isbn_field = form.widget_dict['isbn']
    isbn_field.bind('<FocusOut>', filler)


def get_actions(spec):
    """return a dict of actions suitable for ActionTree.from_map"""
    wrapped_action_ns = {
        k: common.NSWithLogin(getattr(core, k))
        for k in ('Book', 'Person', 'Group', 'Library', 'Borrow', 'Member', 'Script')
    }
    default_action_adapters = {
        'new': lambda name, ns: generic_formbased_action('new', get_form(name), ns.new),
        'edit': lambda name, ns: generic_formbased_action(
            'edit', get_form(name), ns.edit, fill_data=ns.view_ns),
        'view': lambda name, __: ShowInfo.instances.get(name),
        'search': lambda name, ns: actions.search(
            get_form(name + '_search', get_form(name)), ns.search, ShowInfo.instances[name]),
    }
    special_action_funcs = {
        ('Group', 'edit'): generic_formbased_action(
            'edit', forms.GroupForm, wrapped_action_ns['Group'].edit),
        ('Library', 'edit'): generic_formbased_action(
            'edit', forms.LibraryForm, wrapped_action_ns['Library'].edit),
        ('Group', 'activate'): generic_formbased_action(
            None, forms.GroupActivationForm, wrapped_action_ns['Group'].activate),
        ('Member', 'change_password'): generic_formbased_action(
            None, forms.ChangePasswordForm, wrapped_action_ns['Member'].change_password),
        ('Borrow', 'restitute'): generic_formbased_action(
            None, forms.RestituteForm, wrapped_action_ns['Borrow'].restitute),
        ('Book', 'new'): generic_formbased_action(
            'new', forms.BookForm, actions.new_book, post_init=new_book_autofill),
    }

    def get_form(name, *default):
        return getattr(forms, name.title().replace('_', '') + 'Form', *default)

    def set_gui2_action(namespace, func, insert_key):
        if (namespace, func) in special_action_funcs:
            action = special_action_funcs[(namespace, func)]
        else:
            action_ns = wrapped_action_ns[namespace]
            action_adapter = default_action_adapters.get(func)
            if action_adapter is None:
                logging.warning('unknown action "{}"'.format(':'.join((namespace, func))))
                action = None
            else:
                action = action_adapter(namespace, action_ns)
        if action is not None:
            cur_r[insert_key] = action

    RType = T.DefaultDict[str, T.Union['RType', T.Callable[[T.Optional[tk.Event]], None]]]
    r: RType = collections.defaultdict(lambda: collections.defaultdict(r.default_factory))
    for k, v in spec.items():
        cur_r = functools.reduce(operator.getitem, k.split('::')[:-1], r)
        if v['type'] == 'gui2':
            if v['name'] not in wrapped_action_ns:
                logging.warning('unknown action namespace "{}"'.format(v['name']))
                continue
            if v['function'] is None:
                core_ans = getattr(core, v['name'])
                cur_r = cur_r[k]
                action_type = (types.FunctionType, types.MethodType)
                for func_name in dir(core_ans):
                    func_v = getattr(core_ans, func_name)
                    if (func_name.startswith(('_', 'view'))
                            or not isinstance(func_v, action_type)):
                        continue
                    set_gui2_action(v['name'], func_name, func_name)
                set_gui2_action(v['name'], 'view', 'view')
            else:
                set_gui2_action(v['name'], v['function'], k)
        else:
            cur_r[k] = actions.get_script_action(v)
    return r


app = App()

action_tree = ActionTree.from_nested(get_actions(config.gui2.actions.mapping))


lua_callbacks = {
    'ask': partial(tk_msg.askyesno, None),
    'alert': partial(tk_msg.showinfo, None),
    'display': actions.display_lua_data,
    'get_data': actions.handle_lua_get_data,
}
core.Script.callbacks = lua_callbacks
