"""shared utilities"""

import tkinter as tk
import tkinter.messagebox as tk_msg
import typing
import types
import contextlib
import collections
from functools import partial

from .. import core
from .. import utils
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

    @property
    def actions(self):
        """insert actions created through override"""
        return self.ans.actions | self.__overrides[self.ans.__name__].keys()

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

# NOTE: the following functions aren't/shouldn't used anywhere.
# The decorator registers them in NSWithLogin.


@NSWithLogin.override('Book', 'new')
def book_new(**kwargs):
    tk_msg.showinfo(
        utils.get_name('Book'),
        utils.get_name('Book::new_id_{}').format(
            core.Book.new(login_context=main.app.current_login, **kwargs))
    )


@NSWithLogin.override('Book', 'search')
def book_search(condition):
    return core.Book.search(
        (condition, 'and', ('is_active', 'eq', True)),
        login_context=main.app.current_login,
    )


@NSWithLogin.override('Borrow', 'restitute')
def borrow_restitute(book):
    core.Borrow.edit(
        NSWithLogin(core.Book).view_ns(book)['borrow'],
        is_back=True,
        login_context=main.app.current_login,
    )


@NSWithLogin.override('Borrow', 'extend')
def borrow_extend(book, weeks):
    core.Borrow.edit(
        NSWithLogin(core.Book).view_ns(book)['borrow'],
        weeks=weeks,
        login_context=main.app.current_login,
    )
