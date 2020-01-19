"""Objects passed to Lua scripts"""

import abc
import itertools
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

    def lua_get(self, name):
        """provide the requested attribute

            raise AttributeError if not allowed
            this default implementation checks whether
            the name is present in self.get_allowed
        """
        if name not in self.get_allowed:
            raise AttributeError
        return getattr(self, name)

    def lua_set(self, name, value):
        """set the requested attribute

            raise an AttributeError if not allowed
            this default implementation checks whether
            the name is present in self.set_allowed
        """
        if name not in self.set_allowed:
            raise AttributeError
        return setattr(self, name, value)


class LuaActionNS(LuaObject):
    """wrap an ActionNamespace for use with Lua"""
    get_allowed = ('new', 'view_ns', 'edit', 'search')

    def __init__(self, action_ns: T.Type[core.ActionNamespace], **kwargs):
        super().__init__(**kwargs)
        self.action_ns = action_ns
        self.data_ns = LuaDataNS.specific_class[action_ns]

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
    specific_class: T.ClassVar[dict] = {}
    wrap_iter: T.ClassVar[T.Tuple[str, ...]]
    wrap_data_ns: T.ClassVar[T.Dict[str, str]]

    def __init__(self, data_ns, **kwargs):
        super().__init__(**kwargs)
        self.data_ns = data_ns

    @classmethod
    def add_specific(cls,
                     is_for: T.Type[core.ActionNamespace],
                     allow: T.Iterable[str],
                     wrap_iter: T.Iterable[str] = (),
                     wrap_data_ns: T.Mapping[str, T.Type[core.ActionNamespace]] = None):
        """add a subclass with correct access checking"""
        wrap_data_ns = wrap_data_ns or {}
        get_allowed = tuple(itertools.chain(cls.get_allowed, allow))
        new_cls = type('Lua{}DataNS'.format(is_for.__name__), (cls,),
                       {'get_allowed': get_allowed,
                        'wrap_iter': tuple(wrap_iter),
                        'wrap_data_ns': dict(wrap_data_ns)})
        cls.specific_class[is_for] = new_cls

    def lua_get(self, name):
        """enforce wrap_iter ans wrap_data_ns"""
        if name in self.wrap_iter:
            return self.runtime.table(*getattr(self.data_ns, name))
        elif name in self.wrap_data_ns:
            return self.specific_class[self.wrap_data_ns[name]](
                getattr(self.data_ns, name), runtime=self.runtime)
        elif name in self.get_allowed:
            return getattr(self.data_ns, name)
        else:
            return super().lua_get(name)


LuaDataNS.add_specific(core.Book,
                       ('id isbn author title series series_number language publisher '
                        'concerned_people year medium genres shelf is_active').split(),
                       wrap_iter=('groups',),
                       wrap_data_ns={'library': core.Library, 'borrow': core.Borrow})
LuaDataNS.add_specific(core.Person,
                       'id first_name last_name class_ max_borrow pay_date'.split(),
                       ('libraries', 'borrows'))
LuaDataNS.add_specific(core.Library, ('name', 'pay_required'), ('books', 'people'))
LuaDataNS.add_specific(core.Group, ('name',), ('books',))
LuaDataNS.add_specific(core.Borrow, ('id', 'return_date', 'is_back'),
                       wrap_data_ns={'book': core.Book, 'person': core.Person})
LuaDataNS.add_specific(core.Member, ('name', 'level'))
