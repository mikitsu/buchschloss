"""test cli2 main functions"""

import lupa
from buchschloss import cli2
from buchschloss.cli2 import objects
from buchschloss import core


def test_restrict_list():
    rt = lupa.LuaRuntime()
    cli2.restrict_runtime(rt, ['print', 'xpcall', 'doesnotexist'])
    gv = rt.globals()
    assert set(gv)-{'_G', '_VERSION'} == {'print', 'xpcall'}


def test_restrict_nested():
    cmp_rt = lupa.LuaRuntime()
    rt = lupa.LuaRuntime()
    cli2.restrict_runtime(rt, {'io': '*', 'math': [],
                               'string': {'upper': 0, 'lower': 0}})
    gv = rt.globals()
    assert set(gv)-{'_G', '_VERSION'} == {'io', 'math', 'string'}
    assert set(gv['io']) == set(cmp_rt.globals()['io'])
    assert not len(tuple(gv['math']))
    assert set(gv['string']) == {'upper', 'lower'}


def test_table_conversion():
    rt = lupa.LuaRuntime()
    rt.globals()['t'] = cli2.data_to_table(rt, {'a': 123, 'b': ['c', {'d': 'e'}]})
    assert rt.eval("type(t) == 'table' and t.a == 123 and t.b[1] == 'c' and t.b[2].d == 'e'")
    # note: list/tuple is both allowed
    assert (cli2.table_to_data(rt.eval('{a=123, b={"c", {d="e"}}}'))
            == {'a': 123, 'b': ['c', {'d': 'e'}]})


def test_prepare_runtime():
    lc = core.LoginType.INTERNAL(5)
    rt = cli2.prepare_runtime(lc)
    assert not set(rt.globals()) & {'ui', 'storage', 'requests'}
    rt = cli2.prepare_runtime(
        lc,
        add_ui=({'display': lambda x: None}, 'prefix::'),
        add_storage={'x': 123},
        add_requests=True,
    )
    assert len(set(rt.globals()) & {'ui', 'storage', 'requests'}) == 3
    assert rt.eval('storage.x') == 123
    assert isinstance(rt.globals()['ui'], objects.LuaUIInteraction)
    assert rt.globals()['ui'].runtime is rt
    assert isinstance(rt.globals()['requests'], objects.LuaRequestsInterface)
    assert rt.globals()['requests'].runtime is rt
