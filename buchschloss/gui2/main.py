"""GUIv2 for buchschloss"""

import collections.abc
import collections
import functools
import operator
import logging
import tkinter.messagebox as tk_msg
import tkinter.font as tk_font
import tkinter as tk
from tkinter import ttk
from functools import partial
import sys
import typing as T
from typing import MutableMapping

from .. import core
from .. import utils
from .. import config
from ..config.main import DummyErrorFile
from . import widgets
from . import actions
from . import common


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
        ttk.Style().configure('Treeview', rowheight=config.gui2.font.size*2)
        self.current_login = core.guest_lc
        self.on_next_reset = []
        self.greeter = tk.Label(self.root,
                                text=config.gui2.intro.text,
                                font=config.gui2.intro.font)
        self.greeter.pack(fill=tk.BOTH)
        self.center = tk.Frame(self.root)
        self.header = widgets.Header(
            self.root,
            {'text': utils.get_name('action::login'), 'command': actions.login_logout},
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
        common.destroy_all_children(self.center)

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


def get_actions(master, spec):
    """return a dict of actions suitable for ActionTree.from_map"""

    r = collections.defaultdict(lambda: collections.defaultdict(r.default_factory))
    for k, v in spec.items():
        cur_r: MutableMapping = functools.reduce(operator.getitem, k.split('::')[:-1], r)  # noqa
        if v['type'] != 'gui2':
            cur_r[k] = actions.get_script_action(v)
            continue
        name, function = v['name'], v['function']
        if name not in core.ActionNamespace.namespaces:
            logging.warning(f'unknown action namespace "{name}"')
            continue
        ans = common.NSWithLogin(getattr(core, name))
        gui2_actions = [
            a for a in ans.actions
            if not a.startswith(('view',) + ('get_all',) * (name == 'Book'))
        ] + ['view']
        if function is None:
            for a in gui2_actions:
                cur_r[k][f'{k}::{a}'] = actions.make_action(master, name, a)
        elif function in gui2_actions:
            assert isinstance(cur_r, collections.defaultdict)
            cur_r[k] = actions.make_action(master, name, function)
        else:
            logging.warning(f'unknown action: "{name}:{function}"')
    return r


app = App()

action_tree = ActionTree.from_nested(get_actions(app.center, config.gui2.actions.mapping))


lua_callbacks = {
    'ask': partial(tk_msg.askyesno, None),
    'alert': partial(tk_msg.showinfo, None),
    'display': actions.display_lua_data,
    'get_data': actions.handle_lua_get_data,
}
core.Script.callbacks = lua_callbacks
