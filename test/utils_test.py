"""test utils"""
import datetime
import time

from buchschloss import config

config.core.mapping['database name'] = ':memory:'

from buchschloss import core, models, utils, py_scripts  # noqa


def test_get_name():
    """Test get_name"""
    config.utils.names = {
        'a': {
            'b': {
                'c': {
                    '*this*': 'ABC',
                    'd': 'ABCD',
                    'e': 'ABCE',
                },
                'e': 'ABE',
            },
            'c': {
                'd': 'ACD',
                'h': 'ACH',
            },
            'f': 'AF',
        },
        'c': {
            'd': 'CD',
            'h': 'CH',
            'i': 'CI',
        },
        'f': 'F',
        'g': 'G',
    }
    assert utils.get_name('a::b::c::d') == 'ABCD'
    assert utils.get_name('a::b::c') == 'ABC'
    assert utils.get_name('a::b::c::e') == 'ABCE'
    assert utils.get_name('a::b::c::h') == 'ACH'
    assert utils.get_name('a::b::c::f') == 'AF'
    assert utils.get_name('a::b::c::i') == 'CI'
    assert utils.get_name('a::b::c::g') == 'G'
    assert utils.get_name('does::not::exist::at::all::c::d') == 'CD'
    assert utils.get_name('a::b::c__e') == 'ABC: ABCE'
    assert utils.get_name('a::c::h__i') == 'ACH: CI'


def test_script_exec(db, monkeypatch):
    """test correct execution of task scripts"""
    invokes = set()
    monkeypatch.setitem(config.scripts.mapping, 'ui', ({'type': 'cli2', 'name': 'test-1'},))
    monkeypatch.setitem(config.scripts.mapping, 'startup', ({'type': 'py', 'name': 'test_2'},))
    monkeypatch.setitem(config.scripts.mapping, 'repeating', (
        {'type': 'py', 'name': 'test_3', 'invocation': datetime.timedelta(seconds=1)},
        {'type': 'cli2', 'name': 'test-4', 'invocation': datetime.timedelta(minutes=300)},
    ))
    common = dict(permissions=core.ScriptPermissions(0), storage={})
    models.Script.create(name='test-1', code='ui.alert("it works")', **common)
    models.Script.create(name='test-4', code='ui.alert("shouldn\'t happen")', **common)
    get_py_func = lambda name: (lambda callbacks, login_context: invokes.add(name))  # noqa
    monkeypatch.setattr(py_scripts, '__all__', ['test_2', 'test_3'])
    monkeypatch.setattr(py_scripts, 'test_2', get_py_func('test_2'), raising=False)
    monkeypatch.setattr(py_scripts, 'test_3', get_py_func('test_3'), raising=False)
    core.misc_data.last_script_invocations = {
        'test_3!py': datetime.datetime.now() - datetime.timedelta(minutes=15),
        'test-4!cli2': datetime.datetime.now() - datetime.timedelta(minutes=15)
    }
    callbacks = {'alert': invokes.add, 'display': lambda x: None}
    monkeypatch.setattr(core.Script, 'callbacks', callbacks)

    runner = utils.get_runner()
    runner(False)
    runner(False)
    assert invokes == {'test_2', 'test_3'}
    invokes.clear()
    time.sleep(1.5)
    runner(False)
    assert invokes == {'test_3'}
    invokes.clear()
    utils.run_ui_scripts(callbacks=callbacks)
    assert invokes == {utils.get_name('script-data::test-1::it works')}
