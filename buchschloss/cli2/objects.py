"""Objects passed to Lua scripts"""

import abc
import typing as T


class LuaObject(abc.ABC):
    """ABC for object to be passed into the Lua runtime"""
    get_allowed: T.ClassVar[T.Container] = ()
    set_allowed: T.ClassVar[T.Container] = ()

    def allow_get(self, name):
        """decide if the given attribute may be accessed

            raise AttributeError if not allowed
            this default implementation checks whether
            the name is present in self.get_allowed
        """
        if name not in self.get_allowed:
            raise AttributeError

    def allow_set(self, name):
        """decide whether the given attribute may be set

            raise an AttributeError if not allowed
            this default implementation checks whether
            the name is present in self.set_allowed
        """
        if name not in self.set_allowed:
            raise AttributeError
