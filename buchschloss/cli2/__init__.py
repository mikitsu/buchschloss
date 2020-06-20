"""Lua-based cli2"""

import getpass
import traceback
import typing as T
import os

try:
    import lupa
except ImportError as e:
    raise ImportError('did you install cli2-requirements?') from e
try:
    # on linux (all? some?), importing will make arrow keys usable
    import readline
except ImportError:
    pass
from .. import core
from .. import config
from .. import utils
from . import objects


def data_to_table(runtime, data):
    """Convert JSON-type (maps and arrays) data to a lua table"""
    if isinstance(data, (str, int, float, bool, type(None))):
        return data
    if isinstance(data, T.Sequence):
        return runtime.table(*[data_to_table(runtime, d) for d in data])
    elif isinstance(data, T.Mapping):
        return runtime.table_from({k: data_to_table(runtime, v) for k, v in data.items()})
    else:
        raise TypeError("can't handle '{}'".format(type(data)))


def table_to_data(table):
    """convert a Lua table to a dict or a list"""
    if lupa.lua_type(table) == 'table':
        keys = sorted(table.keys())
        if keys == list(range(1, len(keys)+1)):
            return [table_to_data(t) for t in table.values()]
        else:
            return {k: table_to_data(v) for k, v in table.items()}
    else:
        return table


with open(os.path.join(os.path.dirname(__file__), 'builtins.lua')) as f:
    BUILTINS_CODE = f.read()


def lua_set(obj, name, value):
    """delegate attribute setting from Lua"""
    return obj.lua_set(name, value)


def lua_get(obj, name):
    """handle attribute access from Lua, delegating if possible"""
    try:
        return obj.lua_get(name)
    except AttributeError:
        val = getattr(obj, name)
        if isinstance(val, (int, str, float)):
            return val
        else:
            raise AttributeError


def restrict_runtime(runtime, whitelist):
    """restrict a Lua runtime

        ``whitelist`` is container of names of globals to allow.
            if an allowed item is a table, the table values
            will be validated with the whitelist at whitelist[table_name]
            if the whitelist is '*', everything is allowed

            The following whitelist allows 'var_1', 'var_2',
            all of 'table_1', 'table_2.x', 'table_2.y' and
            'table_2.nested.value':
            {'var_1': None, 'var_2': None, 'table_1': '*',
            'table_2': {'x': None, 'y': None, 'nested': ['value']}}

            _G and _VERSION are implicit
    """
    gv = runtime.globals()
    lua_type = gv['type']
    lua_version = gv['_VERSION']

    def allow_values(table, allowed):
        if allowed == '*':
            return
        for k, v in table.items():
            if k not in allowed:
                del table[k]
            elif lua_type(v) == 'table':
                allow_values(v, allowed[k])

    allow_values(gv, whitelist)
    gv['_G'] = gv
    gv['_VERSION'] = lua_version
    return runtime


def prepare_runtime(login_context: core.LoginContext, *,
                    add_ui=None, add_storage=None, add_requests=False, add_config=None):
    """create and initialize a new Lua runtime

    Optional modifiers:
        ``add_ui`` may be (<dict of callbacks>, <script prefix for get_name>)
        ``add_storage`` may be (<getter>, <setter>).
            The objects may consist of basic values, dicts and tuples/lists
        ``add_requests`` indicates whether the script may perform web requests
        ``add_config`` may be a combination of basic values, dicts
            and tuples/lists. It will be assigned to a global variable
    """
    ans_extended_funcs = {
        'Group': ('activate',),
        'Borrow': ('restitute',),
        'Member': ('change_password',),
        'Script': ('execute',),
    }
    # noinspection PyArgumentList
    runtime = lupa.LuaRuntime(attribute_handlers=(lua_get, lua_set))
    restrict_runtime(runtime, config.cli2.whitelist.mapping)
    g = runtime.globals()
    g['buchschloss'] = runtime.table_from({
        k: objects.LuaActionNS(getattr(core, k),
                               login_context=login_context,
                               extra_get_allowed=ans_extended_funcs.get(k, ()),
                               runtime=runtime)
        for k in 'Book Person Group Library Borrow Member Script'.split()
    })
    if add_ui:
        g['ui'] = objects.LuaUIInteraction(*add_ui, runtime=runtime)
    if add_storage is not None:
        getter, setter = add_storage
        g['buchschloss']['get_storage'] = lambda: data_to_table(runtime, getter())
        g['buchschloss']['set_storage'] = lambda d: setter(table_to_data(d))
    if add_requests:
        g['requests'] = objects.LuaRequestsInterface(runtime=runtime)
    if add_config is not None:
        g['config'] = data_to_table(runtime, add_config)
    for k, v in dict(runtime.execute(BUILTINS_CODE)).items():
        g[k] = v
    return runtime


def execute_script(code: str, login_context: core.LoginContext, **kwargs):
    """execute the given code in a new runtime.
        See prepare_runtime for arguments"""
    rt = prepare_runtime(login_context, **kwargs)
    try:
        rt.execute(code)
    except (lupa.LuaError, objects.LuaAccessForbidden):
        traceback.print_exc()


def start():
    """provide a REPL"""
    username = input(utils.get_name('interactive_question::username'))
    if username:
        password = getpass.getpass(utils.get_name('interactive_question::password'))
        try:
            login_context = core.login(username, password)
        except core.BuchSchlossBaseError as e:
            print(e)
            return
    else:
        login_context = core.guest_lc
    rt = prepare_runtime(login_context)
    rt.globals()['getpass'] = getpass.getpass  # for auth_required functions
    while True:
        try:
            line = input(str(login_context)+'@buchschloss-cli2 ==> ')
        except EOFError:
            print()
            return
        try:
            try:
                val = rt.eval(line)
            except lupa.LuaSyntaxError:
                val = rt.execute(line)
        except (lupa.LuaError,
                objects.LuaAccessForbidden,
                core.BuchSchlossBaseError,
                TypeError,
                ) as e:
            print(e)
        except Exception:
            traceback.print_exc()
            print(utils.get_name('unexpected_error'))
        else:
            print(table_to_data(val))
