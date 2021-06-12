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
    assert utils.get_name('c::d::does::not::exist') == 'c::d::does::not::exist'


def test_format_fields():
    config.utils.names = {
        f'model-{i}': {'repr': text} for i, text in enumerate((
            'Literal {{braces}}, also}} this way{{, {0.name}',
            'Uses {0.attr!a} ascii and (invalid) {0.format:spec}',
            '{0.attr2!r:#<&%#JD} with both...',
            'Putt{{ing it {{{{{0.all} together: }}{0.attr!r:37dj}}} {{{0.name}',
        ))
    }
    expected = ({'name'}, {'attr', 'format'}, {'attr2'}, {'all', 'attr', 'name'})
    for i, exp in enumerate(expected):
        assert utils.get_format_fields(f'model-{i}') == exp


def test_script_exec(db, monkeypatch):
    """test correct execution of task scripts"""
    invokes = set()
    monkeypatch.setitem(config.scripts.mapping, 'startup', (
        {'type': 'py', 'name': 'test_2', 'function': None},
        {'type': 'lua', 'name': 'test-5', 'function': 'test'},))
    monkeypatch.setitem(config.scripts.mapping, 'repeating', (
        {'type': 'py', 'name': 'test_3', 'function': None,
         'invocation': datetime.timedelta(seconds=0.1)},
        {'type': 'lua', 'name': 'test-4', 'function': None,
         'invocation': datetime.timedelta(minutes=300)},
    ))
    common = dict(permissions=core.ScriptPermissions(0), storage={})
    models.Script.create(name='test-4', code='ui.alert("shouldn\'t happen")', **common)
    models.Script.create(
        name='test-5', code='return {test=function()ui.alert("yep")end}', **common)
    get_py_func = lambda name: (lambda callbacks, login_context: invokes.add(name))  # noqa
    monkeypatch.setattr(py_scripts, '__all__', ['test_2', 'test_3'])
    monkeypatch.setattr(py_scripts, 'test_2', get_py_func('test_2'), raising=False)
    monkeypatch.setattr(py_scripts, 'test_3', get_py_func('test_3'), raising=False)
    core.misc_data.last_script_invocations = {
        'test_3!py': datetime.datetime.now() - datetime.timedelta(minutes=15),
        'test-4!lua': datetime.datetime.now() - datetime.timedelta(minutes=15)
    }
    callbacks = {'alert': invokes.add, 'display': lambda x: None}
    monkeypatch.setattr(core.Script, 'callbacks', callbacks)

    runner = utils.get_runner()
    runner(False)
    runner(False)
    assert invokes == {'test_2', 'test_3', 'script-data::test-5::yep'}
    invokes.clear()
    time.sleep(0.15)
    runner(False)
    assert invokes == {'test_3'}
    invokes.clear()
