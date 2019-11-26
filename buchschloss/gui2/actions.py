"""Specific actions"""

from .main import tk, tk_msg, app
from .. import core
from .. import utils


def login():
    """log in"""
    if isinstance(core.current_login, core.Dummy):
        try:
            data = mtkd.FormDialog.ask(app.root, forms.LoginForm)
        except mtkd.UserExitedDialog:
            return
        try:
            core.login(**data)
        except core.BuchSchlossBaseError as e:
            tk_msg.showerror(e.title, e.message)
            return
        app.header.set_info_text(utils.get_name('logged_in_as_{}'
                                                ).format(core.current_login))
        app.header.set_login_text(utils.get_name('logout'))
    else:
        core.logout()
        app.header.set_info_text(utils.get_name('logged_out'))
        app.header.set_login_text(utils.get_name('login'))