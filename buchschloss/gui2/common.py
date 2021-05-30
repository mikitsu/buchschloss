"""shared utilities"""

import tkinter as tk
import typing
import types
import contextlib
import collections
from functools import partial

from .. import core
from . import main


class NSWithLogin:
    """Wrap around an ActionNamespace providing the current login"""
    __overrides = collections.defaultdict(dict)

    def __init__(self, ans: typing.Type[core.ActionNamespace]):
        self.ans = ans

    def __getattr__(self, item):
        if item in self.__overrides[self.ans.__name__]:
            return self.__overrides[self.ans.__name__][item]
        val = getattr(self.ans, item)
        if isinstance(val, (types.FunctionType, types.MethodType)):  # noqa
            return lambda *a, **kw: val(*a, login_context=main.app.current_login, **kw)
        else:
            return val

    def __dir__(self):
        # some docs say sequence, some list
        return list({*dir(self.ans), *self.__overrides[self.ans.__name__]})

    @classmethod
    def override(cls, namespace, func_name):
        return partial(cls.__overrides[namespace].__setitem__, func_name)


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


def destroy_all_children(widget: tk.Widget):
    """Destroy all children of the given widget"""
    for child in tuple(widget.children.values()):
        child.destroy()
