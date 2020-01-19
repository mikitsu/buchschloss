"""test cli2 main functions"""

import lupa
from buchschloss import cli2


def test_restrict_list():
    rt = lupa.LuaRuntime()
    cli2.restrict_runtime(rt, ['print', 'xpcall', 'doesnotexist'])
    gv = rt.globals()
    assert set(gv)-{'_G'} == {'print', 'xpcall'}


def test_restrict_nested():
    cmp_rt = lupa.LuaRuntime()
    rt = lupa.LuaRuntime()
    cli2.restrict_runtime(rt, {'io': '*', 'math': [],
                               'string': {'upper': 0, 'lower': 0}})
    gv = rt.globals()
    assert set(gv)-{'_G'} == {'io', 'math', 'string'}
    assert set(gv['io']) == set(cmp_rt.globals()['io'])
    assert not len(tuple(gv['math']))
    assert set(gv['string']) == {'upper', 'lower'}
