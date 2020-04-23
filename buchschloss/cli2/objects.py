"""Objects passed to Lua scripts"""

import abc
import functools
import itertools
import typing as T

import lupa

from .. import core


class LuaAccessForbidden(AttributeError):
    """Subclass of AttributeError for when Lua access to an Attribute is forbidden"""
    def __init__(self, obj, name):
        super().__init__("access to {!r}.{} not possible".format(obj, name))


class CheckLuaAccessForbidden:
    """context manager to suppress AttributeErrors except LuaAccessForbidden"""
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if (not isinstance(exc_val, LuaAccessForbidden)
                and isinstance(exc_val, AttributeError)):
            return True


def table_to_tuple(table):
    """transform a Lua table to a tuple"""
    if lupa.lua_type(table) == 'table':
        return tuple(table_to_tuple(v) for v in dict(table).values())
    else:
        return table


class LuaObject(abc.ABC):
    """ABC for object to be passed into the Lua runtime"""
    get_allowed: T.ClassVar[T.Container] = ()
    set_allowed: T.ClassVar[T.Container] = ()

    def __init__(self, *, runtime: lupa.LuaRuntime, **kwargs):
        """Initialize self"""
        super().__init__(**kwargs)
        self.runtime = runtime

    def lua_get(self, name):
        """provide the requested attribute

            raise AttributeError if not allowed
            this default implementation checks whether
            the name is present in self.get_allowed
        """
        if name not in self.get_allowed:
            raise LuaAccessForbidden(self, name)
        return getattr(self, name)

    def lua_set(self, name, value):
        """set the requested attribute

            raise an AttributeError if not allowed
            this default implementation checks whether
            the name is present in self.set_allowed
        """
        if name not in self.set_allowed:
            raise LuaAccessForbidden
        return setattr(self, name, value)


class LuaActionNS(LuaObject):
    """wrap an ActionNamespace for use with Lua"""
    get_allowed = ('new', 'view_ns', 'edit', 'search')

    def __init__(self, action_ns: T.Type[core.ActionNamespace], login_context, **kwargs):
        super().__init__(**kwargs)
        self.login_context = login_context
        self.action_ns = action_ns
        self.data_ns = LuaDataNS.specific_class[action_ns]

    def lua_get(self, name):
        """Allow access to names stored in self.data_ns"""
        with CheckLuaAccessForbidden():
            return super().lua_get(name)
        # noinspection PyUnreachableCode
        val = getattr(self.action_ns, name)
        if callable(val):
            val = lupa.unpacks_lua_table(
                functools.partial(val, login_context=self.login_context))
        return val

    def search(self, condition):
        """transform the Lua table into a tuple"""
        results = self.action_ns.search(table_to_tuple(condition),
                                        login_context=self.login_context)
        return self.runtime.table(*(self.data_ns(o, runtime=self.runtime) for o in results))

    def view_ns(self, id_):
        """wrap the result in LuaDataNS"""
        return self.data_ns(self.action_ns.view_ns(id_, login_context=self.login_context),
                            runtime=self.runtime)


class LuaDataNS(LuaObject):
    """provide access to data as returned by view_ns"""
    specific_class: 'T.ClassVar[T.Dict[T.Type[core.ActionNamespace, LuaDataNS]]]' = {}
    wrap_iter: 'T.ClassVar[T.Mapping[str, T.Type[LuaDataNS]]]'
    wrap_data_ns: T.ClassVar[T.Mapping[str, T.Type[core.ActionNamespace]]]
    __waiting_specific_class = {}

    def __init__(self, data_ns, **kwargs):
        super().__init__(**kwargs)
        self.data_ns = data_ns

    def __str__(self):
        return str(self.data_ns)

    @classmethod
    def add_specific(cls,
                     is_for: T.Type[core.ActionNamespace],
                     allow: T.Iterable[str],
                     wrap_iter: T.Mapping[str, T.Type[core.ActionNamespace]] = (),
                     wrap_data_ns: T.Mapping[str, T.Type[core.ActionNamespace]] = None):
        """add a subclass with correct access checking"""
        wrap_data_ns = wrap_data_ns or {}
        get_allowed = tuple(itertools.chain(cls.get_allowed, allow))
        wrap_iter = dict(wrap_iter)
        for k, v in wrap_iter.items():
            try:
                wrap_iter[k] = cls.specific_class[v]
            except KeyError:
                cls.__waiting_specific_class.setdefault(v, []).append((is_for, k))
        new_cls = type('Lua{}DataNS'.format(is_for.__name__), (cls,),
                       {'get_allowed': get_allowed,
                        'wrap_iter': dict(wrap_iter),
                        'wrap_data_ns': dict(wrap_data_ns)})
        cls.specific_class[is_for] = new_cls
        if is_for in cls.__waiting_specific_class:
            for k in cls.__waiting_specific_class[is_for]:
                other_cls, other_k = k
                cls.specific_class[other_cls].wrap_iter[other_k] = new_cls
            del cls.__waiting_specific_class[is_for]

    def lua_get(self, name):
        """enforce wrap_iter ans wrap_data_ns"""
        if name in self.wrap_iter:
            return self.runtime.table(*(self.wrap_iter[name](o, runtime=self.runtime)
                                        for o in getattr(self.data_ns, name)))
        elif name in self.wrap_data_ns:
            if getattr(self.data_ns, name) is not None:
                return self.specific_class[self.wrap_data_ns[name]](
                    getattr(self.data_ns, name), runtime=self.runtime)
            else:
                return None
        elif name == '__str__':
            return str(self.data_ns)
        else:
            with CheckLuaAccessForbidden():
                return super().lua_get(name)
            # noinspection PyUnreachableCode
            return getattr(self.data_ns, name)


LuaDataNS.add_specific(core.Book,
                       ('id isbn author title series series_number language publisher '
                        'concerned_people year medium genres shelf is_active').split(),
                       wrap_iter={'groups': core.Group},
                       wrap_data_ns={'library': core.Library, 'borrow': core.Borrow})
LuaDataNS.add_specific(core.Person,
                       'id first_name last_name class_ max_borrow pay_date'.split(),
                       wrap_iter={'libraries': core.Library, 'borrows': core.Borrow})
LuaDataNS.add_specific(core.Library,
                       ('name', 'pay_required'),
                       wrap_iter={'books': core.Book, 'people': core.Person})
LuaDataNS.add_specific(core.Group, ('name',), {'books': core.Book})
LuaDataNS.add_specific(core.Borrow,
                       ('id', 'return_date', 'is_back'),
                       wrap_data_ns={'book': core.Book, 'person': core.Person})
LuaDataNS.add_specific(core.Member, ('name', 'level'))
