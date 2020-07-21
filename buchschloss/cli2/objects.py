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

            raise LuaAccessForbidden if not allowed
            this default implementation checks whether
            the name is present in self.get_allowed
        """
        if name not in self.get_allowed:
            raise LuaAccessForbidden(self, name)
        return getattr(self, name)

    def lua_set(self, name, value):
        """set the requested attribute

            raise LuaAccessForbidden if not allowed
            this default implementation checks whether
            the name is present in self.set_allowed
        """
        if name not in self.set_allowed:
            raise LuaAccessForbidden(self, name)
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
        return self.runtime.table(*(LuaDataNS(o, runtime=self.runtime) for o in results))

    def view_ns(self, id_):
        """wrap the result in LuaDataNS"""
        return LuaDataNS(self.action_ns.view_ns(id_, login_context=self.login_context),
                         runtime=self.runtime)


class LuaDataNS(LuaObject):
    """provide access to data as returned by view_ns"""

    def __init__(self, data_ns, **kwargs):
        super().__init__(**kwargs)
        self.data_ns = data_ns

    def __repr__(self):
        return str(self.data_ns)

    def lua_get(self, name):
        """enforce wrap_iter ans wrap_data_ns"""
        if name.startswith('_'):
            raise LuaAccessForbidden
        else:
            return getattr(self.data_ns, name)


class LuaLoginContext(LuaObject):
    """wrap a LoginContext for consumption by Lua scripts"""
    get_allowed = ('level', 'type', 'name', 'invoker')

    def __init__(self, login_context: core.LoginContext, **kwargs):
        super().__init__(**kwargs)
        self.type = login_context.type.name
        self.level = login_context.level
        self.name = getattr(login_context, 'name', None)
        try:
            inv = login_context.invoker  # noqa
        except AttributeError:
            self.invoker = None
        else:
            self.invoker = type(self)(inv, **kwargs)


class LuaUIInteraction(LuaObject):
    """Provide Lua code a way to interact with the user interface"""
    get_allowed = ('ask', 'alert', 'display', 'get_data', 'get_name', 'get_level')

    def __init__(self, callbacks, script_prefix, **kwargs):
        """provide the callbacks and script-specific prefix for get_name"""
        super().__init__(**kwargs)
        self.script_prefix = script_prefix
        self.callbacks = callbacks
        self.ui_actions = []

        if 'ask' not in callbacks:  # yes, after the assignment
            def ask(question):
                """provide default implementation of 'ask'"""
                return callbacks['get_data']((question, 'key', 'bool'))['key']
            callbacks['ask'] = ask
        callbacks.setdefault('alert', callbacks['display'])
        callbacks.setdefault('register_action', lambda name, cb_id: None)

    @lupa.unpacks_lua_table_method
    def ask(self, question, *format_args, **format_kwargs):
        """ask the user a yes/no question"""
        return self.callbacks['ask'](self.get_name(question, *format_args, **format_kwargs))

    @lupa.unpacks_lua_table_method
    def alert(self, message, *format_args, **format_kwargs):
        """display a short text message"""
        self.callbacks['alert'](self.get_name(message, *format_args, **format_kwargs))

    def display(self, data):
        """display data to the user"""
        return self.callbacks['display'](cli2.table_to_data(data))

    def get_data(self, data_spec):
        """get input from the user. Includes acceptable types (int, str, bool)"""
        data_spec = ((k, self.get_name(k), v) for k, v in
                     cli2.table_to_data(data_spec).items())
        return cli2.data_to_table(self.runtime, self.callbacks['get_data'](data_spec))

    @lupa.unpacks_lua_table_method
    def get_name(self, internal, *format_args, **format_kwargs):
        """provide access to utils.get_name from Lua code"""
        return (utils.get_name(self.script_prefix + internal)
                .format(*format_args, **format_kwargs))

    get_level = staticmethod(utils.get_level)


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
        try:
            r = requests.get(url)
        except requests.RequestException:
            raise core.BuchSchlossError('no_connection', 'no_connection')
        if result == 'auto':
            result = r.headers.get('Content-Type', '').split('/')[-1]
        if result in ('html', 'xml'):
            return LuaBS4Interface(r.text, result, runtime=self.runtime)
        elif result == 'json':
            return cli2.data_to_table(self.runtime, r.json())
        else:
            return r.text
