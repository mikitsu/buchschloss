"""test config"""

import datetime
import base64
import json

from configobj import validate
import pytest
from buchschloss.config import main
from buchschloss.config import validation as config_val


def get_temp_files(tmpdir, number):
    """get ``number`` temporary files"""
    for i in range(number):
        yield tmpdir.join('f' + str(i))


def test_timedelta():
    assert config_val.is_timedelta('1') == datetime.timedelta(days=1)
    assert config_val.is_timedelta('1:1') == datetime.timedelta(days=1, hours=1)
    assert config_val.is_timedelta('1:1:1') == datetime.timedelta(
        days=1, hours=1, minutes=1)
    assert config_val.is_timedelta('0:0:1.5') == datetime.timedelta(minutes=1, seconds=30)
    with pytest.raises(validate.ValidateError):
        config_val.is_timedelta('1::1')
    with pytest.raises(validate.ValidateError):
        config_val.is_timedelta('1:1:1:1')
    with pytest.raises(validate.ValidateError):
        config_val.is_timedelta(':1:1')
    with pytest.raises(validate.ValidateError):
        config_val.is_timedelta(':')


def test_optionlist():
    assert config_val.is_optionlist(list('123'), '1', '2', '3') == list('123')
    assert config_val.is_optionlist(list('aea'), 'a', 'e', 'i', 'o', 'u') == list('aea')
    with pytest.raises(validate.ValidateError):
        config_val.is_optionlist(list('123'), '1', '2', 'not 3')
    with pytest.raises(validate.ValidateError):
        config_val.is_optionlist(['asdf', 'ghjk'], *list('asdfghjk'))


def test_base64bytes():
    assert config_val.is_base64bytes(base64.b64encode(b'\x00\t').decode()) == b'\x00\t'
    assert (config_val.is_base64bytes(base64.b64encode(b'\x00\a').decode(), length=2)
            == b'\x00\a')
    with pytest.raises(validate.ValidateError):
        config_val.is_base64bytes(base64.b64encode(b'\x00\a\t').decode(), length=2)
    with pytest.raises(validate.ValidateError):
        config_val.is_base64bytes(base64.b64encode(b'\x00\t\a').decode() + 'a')
    with pytest.raises(validate.ValidateError):
        config_val.is_base64bytes(['a', 'b'])
    with pytest.raises(validate.ValidateError):
        config_val.is_base64bytes('\tA\a')


def test_script_spec():
    assert config_val.is_script_spec(
        ['asdf-_ q', 'asdf-_ q!py', 'asdf!cli2', 'script:func!cli2', 's:f!py']
    ) == [
        {'name': 'asdf-_ q', 'type': 'cli2', 'function': None},
        {'name': 'asdf-_ q', 'type': 'py', 'function': None},
        {'name': 'asdf', 'type': 'cli2', 'function': None},
        {'name': 'script', 'type': 'cli2', 'function': 'func'},
        {'name': 's', 'type': 'py', 'function': 'f'},  # doesn't really make sense
    ]
    get_td = lambda d, h=0, m=0: datetime.timedelta(days=d, hours=h, minutes=m)
    assert config_val.is_script_spec(
        ['s@1:2:3', 's!py@2:3', 's!cli2@1',  's:f!py@4:5:6'],
        with_time=True,
    ) == [
        {'name': 's', 'type': 'cli2', 'function': None, 'invocation': get_td(1, 2, 3)},
        {'name': 's', 'type': 'py', 'function': None, 'invocation': get_td(2, 3)},
        {'name': 's', 'type': 'cli2', 'function': None, 'invocation': get_td(1)},
        {'name': 's', 'type': 'py', 'function': 'f', 'invocation': get_td(4, 5, 6)},
    ]


# test tasklist later when it's more than just an optionlist wrapper


def test_load_file(tmpdir):
    """test config.main.load_file"""
    f1, f2, f3, f4 = get_temp_files(tmpdir, 4)
    f1.write('a = 1\ninclude = {}'.format(f2))
    f2.write('b = 1\n[sec]\na = 2\ninclude = {},{}'.format(f3, f4))
    f3.write('b = 2')
    f4.write('invalid config file')
    co, errors = main.load_file(f1)
    assert errors == {str(f4)}
    assert co.dict() == {'a': '1', 'b': '1', 'sec': {'a': '2', 'b': '2'}}


def test_load_file_json(tmpdir):
    """test config.main.load_file"""
    f1, f2, f3, f4 = get_temp_files(tmpdir, 4)
    f1.write('{"a": "1", "include": "%s"}' % (f2,))
    f2.write('{"b": "1", "sec": {"a": "2", "include": ["%s", "%s"]}}' % (f3, f4))
    f3.write('{"b": "2"}')
    f4.write('invalid config file')
    co, errors = main.load_file(f1, json.load, json.JSONDecodeError)
    assert errors == {str(f4)}
    assert co.dict() == {'a': '1', 'b': '1', 'sec': {'a': '2', 'b': '2'}}


def test_load_names(tmpdir):
    """test config.main.load_names"""
    file = tmpdir.join('f')
    file.write('{"a": [1, 2, 3], "b": "hello", "c": {"d": "hi"}}')
    default_level_names = {i: 'level_' + str(i) for i in range(main.MAX_LEVEL + 1)}
    assert ({'a': '', 'b': 'hello', 'c': {'d': 'hi'}, 'level names': default_level_names}
            == main.load_names(file, 'json'))
    expected_defaults = (
        '{"0": "only one name"}',
        '{"NaN": "whatever", "0": "IaN"}',
        '"a string"',
        '{"0": "boring", "3": {"very": "interesting"}}',
        '{"123": "a lot", "0": "none"}',
    )
    for default_case in expected_defaults:
        file.write('{"level names": %s}' % default_case)
        assert main.load_names(file, 'json') == {'level names': default_level_names}
    file.write('{"level names": {"4": "four", "6": "six"}}')
    assert main.load_names(file, 'json') == {'level names': {4: 'four', 6: 'six'}}
