"""Utilities. Mostly periodic checks. Everything that is neither core nor gui

contents (for use):
    - get_runner() -- get a task running function
    - send_email() -- send an email
    - check_isbn() -- check an ISBN and convert it to ISBN-13
    - get_name() -- get a pretty name
    - format_date() -- format a date
    - level_names -- get a pretty level representation
    - get_book_data() -- attempt to get data about a book based on the ISBN
"""

import collections
import functools
import itertools
import operator
import email
import smtplib
import ssl
import datetime
import time
import logging
import sched

from buchschloss import core, config, py_scripts


class LevelNameDict(dict):
    """provide defaults for missing level names"""
    def __missing__(self, key):
        return 'level_' + str(key)


def send_email(subject, text):
    """Send an email to the recipient specified in config"""
    cfg = config.utils.email
    msg = email.message.Message()
    msg['From'] = cfg['from']
    msg['To'] = cfg.recipient
    msg['Subject'] = subject
    msg.set_payload(text)
    try:
        with smtplib.SMTP(cfg.smtp.host, cfg.smtp.port) as conn:
            if cfg.smtp.tls:
                conn.starttls(context=ssl.create_default_context())
            if cfg.smtp.username is not None:
                conn.login(cfg.smtp.username, cfg.smtp.password)
            conn.send_message(msg)
    except smtplib.SMTPException as e:
        logging.error('error while sending email: {}: {}'.format(type(e).__name__, e))


def check_isbn(isbn: str) -> int:
    """Check whether the given ISBN is valid and convert it into ISBN-13 format"""
    # To list of digits
    if {'x', 'X'} & set(isbn[:-1]):
        raise ValueError('"X" in not-last position')
    digits = []
    for digit in isbn:
        if digit.isdigit():
            digits.append(int(digit))
        elif digit in 'xX':
            digits.append(10)
    if len(digits) == 9:
        digits.insert(0, 0)
    del isbn
    # check the checksum
    get_weighted_digits = functools.partial(zip, itertools.cycle((1, 3)))
    if len(digits) == 10:
        if (sum((10 - i) * x for i, x in enumerate(digits)) % 11
                or sum(i * x for i, x in enumerate(digits, 1)) % 11):
            raise ValueError('checksum mismatch')
        else:
            digits = [9, 7, 8] + digits[:-1]
            digits.append(-sum(w * d for w, d in get_weighted_digits(digits)) % 10)
    elif len(digits) == 13:
        if sum(w * d for w, d in get_weighted_digits(digits)) % 10:
            raise ValueError('checksum mismatch')
    else:
        raise ValueError(f'ISBN has {len(digits)} digits, not 10 or 13')
    return int(''.join(map(str, digits)))


def get_name(internal: str):
    """Get an end-user suitable name.

    Try lookup in config.utils.names.
    "<namespace>::<name>" may specify a namespace in which lookups are performed first,
        falling back to the global names if nothing is found.
        Namespaces may be nested.
    "__" is replaced by ": " with components (located left/right)
        looked up up individually, with the first (left) acting
        as namespace for the second (right).
    If a name isn't found, a warning is logged and the internal name returned,
        potentially modified
    """
    internal = internal.lower()
    if '__' in internal:
        r = []
        prefix = ''
        for component in internal.split('__'):
            prefix += component
            r.append(get_name(prefix))
            prefix += '::'
        return ': '.join(r)
    *path, name = internal.split('::')
    components = 2**len(path)
    look_in = []
    while components:
        components -= 1
        try:
            look_in.append(functools.reduce(
                operator.getitem,
                (ns for i, ns in enumerate(path, 1) if components & (1 << (len(path) - i))),
                config.utils.names))
        except (KeyError, TypeError):
            pass
    for ns in look_in:
        if isinstance(ns, str):
            continue
        try:
            val = ns[name]
            if isinstance(val, str):
                return val
            elif isinstance(val, dict):
                return val['*this*']
            else:
                raise TypeError('{!r} is neither dict nor str'.format(val))
        except KeyError:
            pass
    name = '::'.join(path + [name])
    if not config.debug:
        logging.warning('Name "{}" was not found in the namefile'.format(name))
    return name


def format_date(date: datetime.date):
    """format a date object as specified in config"""
    if date is None:
        return '-----'
    else:
        return date.strftime(config.utils.names.date)


def get_book_data(isbn: int):
    """Attempt to get book data via the ISBN from the DB and configured scripts"""
    def get_data_from_script(script_spec):
        get_script_target(
            script_spec,
            ui_callbacks={
                'get_data': lambda __: {'isbn': isbn},
                'display': data.update,
            },
            login_context=core.internal_unpriv_lc,
        )()

    try:
        book = next(iter(core.Book.search(
            ('isbn', 'eq', isbn), login_context=core.internal_priv_lc)))
    except StopIteration:
        data = {}
        for spec in config.utils.book_data_scripts:
            try:
                get_data_from_script(spec)
            except core.BuchSchlossBaseError as e:
                logging.warning(
                    f'Error "{e.title}" fetching data for {isbn}: {e.message}')
    else:
        data = dict(core.Book.view_ns(book['id'], login_context=core.internal_priv_lc))
    for k in ('id', 'borrow', 'is_active'):
        data.pop(k, None)
    return data


def get_script_target(spec, *, ui_callbacks=None, login_context, propagate_bse=False):
    """get a script target function"""
    if spec['type'] == 'py':
        if spec['name'] in py_scripts.__all__:
            target = functools.partial(
                getattr(py_scripts, spec['name']),
                callbacks=ui_callbacks,
                login_context=login_context
            )
        else:
            target = functools.partial(
                logging.error, 'no such script: {}!py'.format(spec['name']))
    elif spec['type'] == 'lua':
        target = functools.partial(
            core.Script.execute,
            spec['name'],
            spec['function'],
            callbacks=ui_callbacks,
            login_context=login_context,
        )
    else:
        raise AssertionError("spec['type'] == {0[type]!r} not in ('py', 'lua')"
                             .format(spec))

    def wrapped_target():
        """handle errors while executing script"""
        try:
            target()
        except Exception as e:
            if isinstance(e, core.BuchSchlossBaseError) and propagate_bse:
                raise
            elif config.debug:
                raise
            else:
                logging.error('error while executing script {}: {}'
                              .format(spec['complete_spec'], e))
    return wrapped_target


def get_runner():
    """return a function that runs all startup tasks and schedules repeating tasks"""
    scheduler = sched.scheduler(timefunc=time.time)
    for spec in config.scripts.startup:
        target = get_script_target(spec, login_context=core.internal_unpriv_lc)
        scheduler.enter(0, 0, target)

    last_invocations = collections.defaultdict(
        lambda: datetime.datetime.fromtimestamp(0), core.misc_data.last_script_invocations)
    for spec in config.scripts.repeating:
        target = get_script_target(spec, login_context=core.internal_unpriv_lc)
        script_id = '{0[name]}!{0[type]}'.format(spec)
        delay = spec['invocation'].total_seconds()
        invoke_time: datetime.datetime = last_invocations[script_id] + spec['invocation']

        def target_wrapper(_f, _t=target, _id=script_id, _delay=delay):
            _t()
            last_invs = core.misc_data.last_script_invocations
            last_invs[_id] = datetime.datetime.now()
            core.misc_data.last_script_invocations = last_invs
            scheduler.enter(_delay, 0, functools.partial(_f, _f))

        scheduler.enterabs(invoke_time.timestamp(), 0,
                           functools.partial(target_wrapper, target_wrapper))

    return scheduler.run


level_names = LevelNameDict(config.utils.names.level_names.mapping)
