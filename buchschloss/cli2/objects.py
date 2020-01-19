"""Objects passed to Lua scripts"""

import abc
import typing as T

import lupa

from .. import core


class LuaObject(abc.ABC):
    """ABC for object to be passed into the Lua runtime"""
    get_allowed: T.ClassVar[T.Container] = ()
    set_allowed: T.ClassVar[T.Container] = ()

    def __init__(self, *, runtime: lupa.LuaRuntime, **kwargs):
        """Initialize self"""
        super().__init__(**kwargs)
        self.runtime = runtime

    def allow_get(self, name):
        """decide if the given attribute may be accessed

            raise AttributeError if not allowed
            this default implementation checks whether
            the name is present in self.get_allowed
        """
        if name not in self.get_allowed:
            raise AttributeError
        return name

    def allow_set(self, name):
        """decide whether the given attribute may be set

            raise an AttributeError if not allowed
            this default implementation checks whether
            the name is present in self.set_allowed
        """
        if name not in self.set_allowed:
            raise AttributeError
        return name


class LuaActionNS(LuaObject):
    """wrap an ActionNamespace for use with Lua"""
    get_allowed = ('new', 'view_ns', 'edit', 'search')

    def __init__(self, action_ns: core.ActionNamespace, **kwargs):
        super().__init__(**kwargs)
        self.action_ns = action_ns

    def search(self, condition):
        """transform the Lua table into a tuple"""
        def transform(table):
            if lupa.lua_type(table) == 'table':
                return tuple(transform(v) for v in table)
            else:
                return table

        results = self.action_ns.search(transform(condition))
        return self.runtime.table(*(LuaDataNS(o, runtime=self.runtime) for o in results))

    def view_ns(self, id_):
        """wrap the result in LuaDataNS and return None on failure"""
        try:
            return LuaDataNS(self.action_ns.view_ns(id_), runtime=self.runtime)
        except core.BuchSchlossBaseError:
            return None


class LuaDataNS(LuaObject):
    """provide access to data as returned by view_ns"""
    def __init__(self, data_ns, **kwargs):
        super().__init__(**kwargs)
        self.data_ns = data_ns
