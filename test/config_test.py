"""test config"""

import datetime
from configobj import validate
import pytest
from buchschloss import config


def test_timedelta():
    assert config.is_timedelta('1') == datetime.timedelta(days=1)
    assert config.is_timedelta('1:1') == datetime.timedelta(days=1, hours=1)
    assert config.is_timedelta('1:1:1') == datetime.timedelta(
        days=1, hours=1, minutes=1)
    assert config.is_timedelta('0:0:1.5') == datetime.timedelta(minutes=1, seconds=30)
    with pytest.raises(validate.ValidateError):
        config.is_timedelta('1::1')
    with pytest.raises(validate.ValidateError):
        config.is_timedelta('1:1:1:1')
    with pytest.raises(validate.ValidateError):
        config.is_timedelta(':1:1')
    with pytest.raises(validate.ValidateError):
        config.is_timedelta(':')


def test_optionlist():
    assert config.is_optionlist(list('123'), '1', '2', '3') == list('123')
    assert config.is_optionlist(list('aea'), 'a', 'e', 'i', 'o', 'u') == list('aea')
    with pytest.raises(validate.ValidateError):
        config.is_optionlist(list('123'), '1', '2', 'not 3')
    with pytest.raises(validate.ValidateError):
        config.is_optionlist(['asdf', 'ghjk'], *list('asdfghjk'))


# test tasklist later whin it's more than just an optionlist wrapper
