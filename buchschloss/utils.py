"""Utilities. Mostly periodic checks. Everything that is neither core nor gui

contents (for use):
    - get_runner() -- get a task running function
    - send_email() -- send an email
    - get_name() -- get a pretty name
    - get_book_data() -- attempt to get data about a book based on the ISBN

to add late handlers, append them to late_handlers.
they will receive arguments as specified in late_books
"""

import collections
import functools
import operator
import email
import smtplib
import ssl
from datetime import datetime, date
import time
import requests
import logging
import re
import sched
import bs4

from buchschloss import core, config, py_scripts


class FormattedDate(date):
    """print a datetime.date as specified in config.core.date_format"""

    def __str__(self):
        return self.strftime(config.core.date_format)

    @classmethod
    def fromdate(cls, date_: date):
        """Create a FormattedDate from a datetime.date"""
        if date_ is None:
            return None
        else:
            return cls(date_.year, date_.month, date_.day)

    def todate(self):
        """transform self to a datetime.date"""
        return date(self.year, self.month, self.day)


def late_books():
    """Check for late and nearly late books.

    Call the functions in late_handlers with arguments (late, warn).
    late and warn are sequences of core.Borrow instances.
    """
    late = []
    warn = []
    today = date.today()
    warn_for = today + config.utils.tasks.late_books_warn_time
    for b in core.Borrow.search((
            ('is_back', 'eq', False), 'and', ('return_date', 'gt', warn_for)),
            login_context=core.internal_lc):
        if b.return_date < today:
            late.append(b)
        else:
            warn.append(b)
    for h in late_handlers:
        h(late, warn)


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
        except KeyError:
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


def get_level(number: int = None):
    """get the level name corresponding to the given number
        or a sequence of all level names"""
    if number is None:
        return config.utils.names.level_names
    else:
        return config.utils.names.level_names[number]


def get_book_data(isbn: int):
    """Attempt to get book data via the ISBN from the DB, if that fails,
        try the DNB (https://portal.dnb.de)"""
    def get_data_from_script(script_spec):
        get_script_target(
            script_spec,
            ui_callbacks={
                'get_data': lambda __: {'isbn': isbn},
                'display': data.update,
            },
            login_context=core.internal_lc,
        )()

    data = {}
    for spec in config.utils.book_data_scripts:
        get_data_from_script(spec)
    try:
        book = next(iter(core.Book.search(
            ('isbn', 'eq', isbn), login_context=core.internal_lc)))
    except StopIteration:
        pass
    else:
        new_data = core.Book.view_str(book.id, login_context=core.internal_lc)
        del new_data['id'], new_data['status'], new_data['return_date']
        del new_data['borrowed_by_id'], new_data['__str__'], new_data['borrowed_by']
        data.update(new_data)

    return data


def get_script_target(spec, *, ui_callbacks=None, login_context, propagate_bse=False):
    """get a script target function"""
    if spec['type'] == 'py':
        if spec['name'] in py_scripts.__all__:
            return functools.partial(getattr(py_scripts, spec['name']),
                                     callbacks=ui_callbacks,
                                     login_context=login_context)
        return functools.partial(logging.error, 'no such script: {}!py'.format(spec['name']))
    elif spec['type'] == 'cli2':
        def target(_name=spec['name'], _func=spec['function']):
            try:
                core.Script.execute(
                    _name, _func, callbacks=ui_callbacks, login_context=login_context)
            except Exception as e:
                if isinstance(e, core.BuchSchlossBaseError) and propagate_bse:
                    raise
                elif config.debug:
                    raise
                else:
                    logging.error('error while executing script {}!cli2: {}'.format(_name, e))
        return target
    else:
        raise AssertionError("spec['type'] == {0[type]!r} not in ('py', 'cli2')"
                             .format(spec))


def get_runner():
    """return a function that runs all startup tasks and schedules repeating tasks"""
    scheduler = sched.scheduler(timefunc=time.time)
    for spec in config.scripts.startup:
        scheduler.enter(0, 0, get_script_target(spec, login_context=core.internal_lc))

    last_invocations = collections.defaultdict(
        lambda: datetime.fromtimestamp(0), core.misc_data.last_script_invocations)
    for spec in config.scripts.repeating:
        target = get_script_target(spec, login_context=core.internal_lc)
        script_id = '{0[name]}!{0[type]}'.format(spec)
        invoke_time: datetime = last_invocations[script_id] + spec['invocation']

        def target_wrapper(_f, _t=target, _id=script_id, _delay=spec['invocation'].total_seconds()):
            _t()
            last_invs = core.misc_data.last_script_invocations
            last_invs[_id] = datetime.now()
            core.misc_data.last_script_invocations = last_invs
            scheduler.enter(_delay, 0, functools.partial(_f, _f))

        scheduler.enterabs(invoke_time.timestamp(), 0,
                           functools.partial(target_wrapper, target_wrapper))

    return scheduler.run


def _default_late_handler(late, warn):
    head = datetime.now().strftime(config.core.date_format).join(('\n\n',))
    with open('late.txt', 'w') as f:
        f.write(head)
        f.write('\n'.join(str(L) for L in late))
    with open('warn.txt', 'w') as f:
        f.write(head)
        f.write('\n'.join(str(w) for w in warn))


late_handlers = [_default_late_handler]
