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
        width -= (orphan_n < orphan_nm1)
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
                    try:
                        _f()
                    except core.BuchSchlossBaseError as e:
                        tk_msg.showerror(e.title, e.message)
                        app.reset()
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


def get_actions(spec):
    """return a dict of actions suitable for ActionTree.from_map"""
    gfa = generic_formbased_action
    wrapped_action_ns = {
        k: common.NSWithLogin(getattr(core, k))
        for k in core.ActionNamespace.namespaces
    }
    default_action_adapters = {
        'new': lambda name, ns: gfa('new', get_form(name), ns.new),
        'edit': lambda name, ns: gfa(
            'edit', get_form(name), ns.edit, fill_data=ns.view_ns),
        'view': lambda name, __: ShowInfo.instances.get(name),
        'search': lambda name, ns: actions.search(
            get_form(name + 'Search', get_form(name)), ns.search, ShowInfo.instances[name]),
    }
    special_action_funcs = {
        ('Library', 'edit'): gfa(
            'edit', forms.LibraryForm, wrapped_action_ns['Library'].edit),
        ('Book', 'new'): gfa(  # not through override because of post_init
            'new', forms.BookForm, actions.new_book, post_init=new_book_autofill),
        ('Book', 'search'): actions.search(
            forms.BookForm,
            lambda c: wrapped_action_ns['Book'].search((c, 'and', ('is_active', 'eq', True))),
            actions.ShowInfo.instances['Book'],
        )
    }

    def get_form(name, *default):
        return getattr(forms, name + 'Form', *default)

    def get_gui2_action(namespace, func):
        if (namespace, func) in special_action_funcs:
            return special_action_funcs[(namespace, func)]
        action_ns = wrapped_action_ns[namespace]
        action_adapter = default_action_adapters.get(func)
        if action_adapter is not None:
            return action_adapter(namespace, action_ns)
        special_func = getattr(action_ns, func, None)
        if special_func is None:
            logging.warning('unknown action "{}"'.format(':'.join((namespace, func))))
            return None
        else:
            form_name = namespace.capitalize() + func.title().replace('_', '')
            return gfa(None, get_form(form_name), special_func)

    def set_gui2_action(namespace, func, insert_key):
        action = get_gui2_action(namespace, func)
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
                core_ans = wrapped_action_ns[v['name']]
                cur_r = cur_r[k]
                action_type = (types.FunctionType, types.MethodType)
                for func_name in dir(core_ans):
                    func_v = getattr(core_ans, func_name)
                    if any((func_name.startswith(('_', 'view')),
                            not isinstance(func_v, action_type),
                            v['name'] == 'Book' and func_name.startswith('get_all'),
                            )):
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
