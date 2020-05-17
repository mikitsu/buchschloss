"""Objects passed to Lua scripts"""

import abc
import functools
import itertools
import typing as T
import warnings

import lupa
import bs4
import requests

from .. import utils
from .. import core
from .. import cli2
from .. import config


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

    def __init__(self, action_ns: T.Type[core.ActionNamespace],
                 login_context: core.LoginContext,
                 extra_get_allowed: T.Tuple[str, ...] = (),
                 **kwargs):
        super().__init__(**kwargs)
        self.get_allowed += extra_get_allowed
        self.login_context = login_context
        self.action_ns = action_ns
        self.data_ns = LuaDataNS.specific_class[action_ns]

    def lua_get(self, name):
        """Allow access to names stored in self.action_ns"""
        with CheckLuaAccessForbidden():
            return super().lua_get(name)
        # noinspection PyUnreachableCode
        val = getattr(self.action_ns, name)
        if callable(val):
            @lupa.unpacks_lua_table
            def func(*args, **kwargs):
                args = map(cli2.table_to_data, args)
                kwargs = {k: cli2.table_to_data(v) for k, v in kwargs.items()}
                return val(*args, login_context=self.login_context, **kwargs)
            return func
        else:
            return val

    def search(self, condition):
        """transform the Lua table into a tuple"""
        results = self.action_ns.search(cli2.table_to_data(condition),
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


class LuaUIInteraction(LuaObject):
    """Provide Lua code a way to interact with the user interface"""
    get_allowed = ('ask', 'alert', 'display', 'get_data', 'get_name')

    def __init__(self, callbacks, script_prefix, **kwargs):
        """provide the callbacks and script-specific prefix for get_name"""
        super().__init__(**kwargs)
        self.script_prefix = script_prefix
        self.callbacks = callbacks

        if 'ask' not in callbacks:  # yes, after the assignment
            def ask(question):
                """provide default implementation of 'ask'"""
                return callbacks['get_data']((question, 'key', 'bool'))['key']
            callbacks['ask'] = ask
        callbacks.setdefault('alert', callbacks['display'])

    @lupa.unpacks_lua_table_method
    def ask(self, question, *format_args, **format_kwargs):
        """ask the user a yes/no question"""
        return self.callbacks['ask'](self.get_name(question)
                                     .format(*format_args, **format_kwargs))

    @lupa.unpacks_lua_table_method
    def alert(self, message, *format_args, **format_kwargs):
        """display a short text message"""
        self.callbacks['alert'](self.get_name(message)
                                .format(*format_args, **format_kwargs))

    def display(self, data):
        """display data to the user"""
        return self.callbacks['display'](cli2.table_to_data(data))

    def get_data(self, data_spec):
        """get input from the user. Includes acceptable types (int, str, bool)"""
        data_spec = ((k, self.get_name(k), v) for k, v in cli2.table_to_data(data_spec))
        return cli2.data_to_table(self.runtime, self.callbacks['get_data'](data_spec))

    @lupa.unpacks_lua_table_method
    def get_name(self, internal, *format_args, **format_kwargs):
        """provide access to utils.get_name from Lua code"""
        return (utils.get_name(self.script_prefix + internal)
                .format(*format_args, **format_kwargs))


class LuaBS4Interface(LuaObject):
    """Provide Lua code an interface to bs4"""
    get_allowed = ('select', 'select_one', 'attrs', 'text')

    def __init__(self, markup, features=None, **kwargs):
        super().__init__(**kwargs)
        if isinstance(markup, bs4.Tag):
            self.tag = markup
        else:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', 'No parser was')
                self.tag = bs4.BeautifulSoup(markup, features=features)
        self.text = self.tag.get_text()
        self.attrs = cli2.data_to_table(self.runtime, self.tag.attrs)

    def __str__(self):
        return str(self.tag)

    def select(self, selector):
        """wrap bs4.Tag's .select"""
        return self.runtime.table(*map(
            functools.partial(type(self), runtime=self.runtime),
            self.tag.select(selector)))

    def select_one(self, selector):
        """wrap bs4.Tag's .select_one"""
        r = self.tag.select_one(selector)
        if r is None:
            return None
        else:
            return type(self)(r, runtime=self.runtime)


class LuaRequestsInterface(LuaObject):
    """Provide Lua code an interface to requests"""
    get_allowed = config.cli2.requests.methods

    def get(self, url, result='auto'):
        """wrap requests.get"""
        if config.cli2.requests.url_regex.search(url) is None:
            return None
        r = requests.get(url)
        if result == 'auto':
            result = r.headers.get('Content-Type', '').split('/')[-1]
        if result in ('html', 'xml'):
            return LuaBS4Interface(r.text, result, runtime=self.runtime)
        elif result == 'json':
            return cli2.data_to_table(self.runtime, r.json())
        else:
            return r.text


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
LuaDataNS.add_specific(core.Script, ('code', 'setlevel', 'name'))
