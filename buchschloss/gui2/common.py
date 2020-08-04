"""shared utilities"""

import typing
import contextlib

from .. import core
from . import main


class NSWithLogin:
    """Wrap around an ActionNamespace providing the current login"""
    def __init__(self, ans: typing.Type[core.ActionNamespace]):
        self.ans = ans

    def __getattr__(self, item):
        val = getattr(self.ans, item)
        if callable(val):
            return lambda *a, **kw: val(*a, login_context=main.app.current_login, **kw)
        else:
            return val


@contextlib.contextmanager
def ignore_missing_messagebox():
    """ignore KeyError('__tk__messagebox')"""
    try:
        yield
    except KeyError as e:
        if str(e) == "'__tk__messagebox'":
            return
        else:
            raise
