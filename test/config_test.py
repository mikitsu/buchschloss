"""test config"""

import datetime
import base64
import json

from configobj import validate
import pytest
from buchschloss import config
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


# test tasklist later when it's more than just an optionlist wrapper


def test_load_file(tmpdir):
    """test config.load_file"""
    f1, f2, f3, f4 = get_temp_files(tmpdir, 4)
    f1.write('a = 1\ninclude = {}'.format(f2))
    f2.write('b = 1\n[sec]\na = 2\ninclude = {},{}'.format(f3, f4))
    f3.write('b = 2')
    f4.write('invalid config file')
    co, errors = config.load_file(f1)
    assert errors == {str(f4)}
    assert co.dict() == {'a': '1', 'b': '1', 'sec': {'a': '2', 'b': '2'}}


def test_load_file_json(tmpdir):
    """test config.load_file"""
    f1, f2, f3, f4 = get_temp_files(tmpdir, 4)
    f1.write('{"a": "1", "include": "%s"}' % (f2,))
    f2.write('{"b": "1", "sec": {"a": "2", "include": ["%s", "%s"]}}' % (f3, f4))
    f3.write('{"b": "2"}')
    f4.write('invalid config file')
    co, errors = config.load_file(f1, json.load, json.JSONDecodeError)
    assert errors == {str(f4)}
    assert co.dict() == {'a': '1', 'b': '1', 'sec': {'a': '2', 'b': '2'}}
