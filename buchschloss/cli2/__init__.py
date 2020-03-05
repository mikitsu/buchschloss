"""Lua-based cli2"""

try:
    import lupa
except ImportError as e:
    raise ImportError('did you install cli2-requirements?') from e
from .. import core
from .. import config
from . import objects


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


def prepare_runtime():
    """create and initialize a new Lua runtime"""
    # noinspection PyArgumentList
    runtime = lupa.LuaRuntime(attribute_handlers=(lambda o, n: o.lua_get(n),
                                                  lambda o, n, v: o.lua_set(n, v)))
    restrict_runtime(runtime, config.cli2.whitelist.mapping)
    runtime.globals()['buchschloss'] = {
        k: objects.LuaActionNS(getattr(core, k))
        for k in 'Book Person Group Library Borrow Member'.split()
    }
    return runtime
