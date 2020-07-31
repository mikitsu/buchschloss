"""Validation extensions"""

import datetime
import os
import base64
import binascii
import re

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


def is_script_spec(value,
                   with_time=False,
                   single=False,
                   suffixes=('cli2', 'py'),
                   default_suffix='cli2'):
    """check whether the value is syntactically a script spec and return components"""
    spec_regex_parts = [
        r'^\s*(?P<name>[-\w ]+)(?::(?P<function>\w+))?',
        '|'.join(suffixes).join((r'(?:!(?P<type>', '))?')),
    ]
    if with_time:
        spec_regex_parts.append(r'@(?P<invocation>\d+(?::\d+(?::\d+)?)?)')
    spec_regex = re.compile(''.join(spec_regex_parts) + r'\s*$')
    if isinstance(value, str):
        value = value.split(',')
    r = []
    for v in value:
        m = spec_regex.match(v)
        if m is None:
            raise validate.VdtValueError(v)
        else:
            script_data = m.groupdict()
            script_data['type'] = script_data['type'] or default_suffix
            if 'invocation' in script_data:
                script_data['invocation'] = is_timedelta(script_data['invocation'])
            r.append(script_data)
    if single:
        if len(r) != 1:
            raise validate.VdtTypeError(value)
        r = r[0]
    return r


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


def is_regex(value):
    """check whether the value is a valid regex and compile it"""
    try:
        return re.compile(value)
    except re.error:
        raise validate.VdtValueError(value)


validator = validate.Validator({
    'level_number': lambda v: validate.is_integer(v, 0, MAX_LEVEL),
    'timedelta': is_timedelta,
    'optionlist': is_optionlist,
    'script_spec': is_script_spec,
    'file': is_file,
    'base64bytes': is_base64bytes,
    'regex': is_regex,
})
