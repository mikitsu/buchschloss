"""Validation extensions"""

import datetime
import os
import base64
import binascii

from configobj import validate

MAX_LEVEL = 10


def is_timedelta(value):
    """create timedeltas"""
    if isinstance(value, (int, float)):
        return datetime.timedelta(days=value)
    elif isinstance(value, str):
        if value.count(':') > 2:
            raise validate.VdtValueError(value)
        try:
            items = [(n, float(x)) for n, x in zip(
                ('days', 'hours', 'minutes'), value.split(':'))]
        except ValueError:
            raise validate.VdtTypeError(value)
        return datetime.timedelta(**dict(items))
    else:
        raise validate.VdtTypeError(value)


def is_optionlist(value, *options):
    """check whether all list items are in ``options``"""
    try:
        if not all(isinstance(v, str) for v in options):
            raise validate.VdtParamError(options, value)
    except TypeError as e:
        raise validate.VdtParamError(str(e), value)
    val = validator.check('force_list', value)
    if not all(v in options for v in val):
        raise validate.VdtValueError(value)
    return val


def is_task_list(value, _tasks=('backup', 'ftp_backup', 'late_books', 'http_backup')):
    """check whether the value is a list of tasks"""
    # TODO: make ``_tasks`` a mapping directly to the functions
    return validator.check('optionlist{}'.format(_tasks), value)


def is_file(value):
    """check whether the value is a valid file system path"""
    if not isinstance(value, str):
        raise validate.VdtTypeError(value)
    if not os.path.isfile(value):
        raise validate.VdtValueError(value)
    return value


def is_base64bytes(value, length=None):
    """check whether the value is ``length`` base64-encoded bytes

        if ``length`` is not given, allow any length
    """
    if length is not None:
        length = int(length)
    if not isinstance(value, str):
        raise validate.VdtTypeError(value)
    try:
        data = base64.b64decode(value)
    except binascii.Error:
        raise validate.VdtValueError(value)
    if length is not None and len(data) != length:
        raise validate.VdtValueError(value)
    return data


validator = validate.Validator({
    'level_number': lambda v: validate.is_integer(v, 0, MAX_LEVEL),
    'timedelta': is_timedelta,
    'optionlist': is_optionlist,
    'task_list': is_task_list,
    'file': is_file,
    'base64bytes': is_base64bytes,
})
