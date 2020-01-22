"""Utilities. Mostly periodic checks. Everything that is neither core nor gui

contents (for use):
    - run() -- call once on startup. takes care of all automatic tasks
    - send_email() -- send an email
    - get_name() -- get a pretty name
    - get_book_data() -- attempt to get data about a book based on the ISBN
        (first local DB, then DNB).

to add late handlers, append them to late_handlers.
they will receive arguments as specified in late_books
"""

import base64
import tempfile
import email
import smtplib
import ssl
from datetime import datetime, timedelta, date
import time
import threading
import shutil
import os
import ftplib
import ftputil
import requests
import logging
import re
import bs4
import string

try:
    from cryptography import fernet
except ImportError:
    fernet = None

from buchschloss import core, config


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


def run_checks():
    """Run stuff to do as specified by times set in config"""
    while True:
        if datetime.now() > core.misc_data.check_date + timedelta(minutes=45):
            for stuff in stuff_to_do:
                threading.Thread(target=stuff).start()
            core.misc_data.check_date = datetime.now() + config.utils.tasks.repeat_every
        time.sleep(5 * 60 * 60)


def late_books():
    """Check for late and nearly late books.

    Call the functions in late_handlers with arguments (late, warn).
    late and warn are sequences of core.Borrow instances.
    """
    late = []
    warn = []
    today = date.today()
    for b in core.Borrow.search((
            ('is_back', 'eq', False),
            'and', ('return_date', 'gt', today + config.utils.late_books_warn_time))):
        if b.return_date < today:
            late.append(b)
        else:
            warn.append(b)
    for h in late_handlers:
        h(late, warn)


def backup():
    """Local backups.

    Run backup_shift and copy "name" db to "name.1", encrypting if a key is given in config
    """
    backup_shift(os, config.utils.tasks.backup_depth)
    data = get_database_bytes()
    with open(config.core.database_name + '.1', 'wb') as f:
        f.write(data)


def get_database_bytes():
    """get the contents of the database file,
        encrypted if a key is specified in config"""
    with open(config.core.database_name, 'rb') as f:
        plain = f.read()
    if config.utils.tasks.secret_key is None:
        return plain
    if fernet is None:
        raise RuntimeError('encryption requested, but no cryptography available')
    key = base64.urlsafe_b64encode(config.utils.tasks.secret_key)
    cipher = fernet.Fernet(key).encrypt(plain)
    return base64.urlsafe_b64decode(cipher)


def ftp_backup():
    """Remote backups via FTP.

    Run backup_shift and upload "name" DB as "name.1", encrypted if a key is given in config
    """
    conf = config.utils
    if conf.tasks.secret_key is None:
        upload_path = config.core.database_name
        file = None
    else:
        file = tempfile.NamedTemporaryFile(delete=False)
        file.write(get_database_bytes())
        file.close()
        upload_path = file.name

    factory = ftplib.FTP_TLS if conf.ftp.tls else ftplib.FTP
    # noinspection PyDeprecation
    with ftputil.FTPHost(conf.ftp.host, conf.ftp.username, conf.ftp.password,
                         session_factory=factory, use_list_a_option=False) as host:
        backup_shift(host, conf.tasks.web_backup_depth)
        host.upload(upload_path, config.core.database_name + '.1')
    if file is not None:
        os.unlink(file.name)


def http_backup():
    """remote backups via HTTP"""
    conf = config.utils.http
    data = get_database_bytes()
    options = {}
    if conf.authentication.username:
        options['auth'] = (conf.authentication.username,
                           conf.authentication.password)
    r = requests.post(conf.url, files={conf.file_name: data}, **options)
    if r.status_code != 200:
        logging.error('received unexpected status code {} during HTTP backup'
                      .format(r.status_code))


def backup_shift(fs, depth):
    """shift all name.number up one number to the given depth
        in the given filesystem (os or remote FTP host)"""
    number_name = lambda n: '.'.join((config.core.database_name, str(n)))  # noqa
    try:
        fs.remove(number_name(depth))
    except FileNotFoundError:
        pass
    for f in range(depth, 1, -1):
        try:
            fs.rename(number_name(f - 1), number_name(f))
        except FileNotFoundError:
            pass


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
    "__" is replaced by ": " with components looked up individually
    If a name isn't found, a warning is logged and the internal name returned,
        potentially modified
    "<namespace>::<name>" may specify a namespace in which lookups are performed first,
        falling back to the global names if nothing is found
    "__" takes precedence over "::"
    """
    if '__' in internal:
        return ': '.join(get_name(s) for s in internal.split('__'))
    *path, name = internal.split('::')
    current = config.utils.names
    look_in = [current]
    try:
        for k in path:
            current = current[k]
            look_in.append(current)
    except KeyError:
        if not config.debug:
            # noinspection PyUnboundLocalVariable
            logging.warning('invalid namespace {!r} of {!r}'.format(k, internal))
    look_in.reverse()
    for ns in look_in:
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


def break_string(text, size, break_char=string.punctuation, cut_char=string.whitespace):
    """Insert newlines every `size` characters.

        Insert '\n' before the given amount of characters
        if a character in `break_char` is encountered.
        If the character is in `cut_char`, it is replaced by the newline.
    """
    # TODO: move to misc
    break_char += cut_char
    r = []
    while len(text) > size:
        i = size
        cut = False
        while i:
            if text[i] in break_char:
                cut = text[i] in cut_char
                break
            i -= 1
        else:
            i = size - 1
        i += 1
        r.append(text[:i - cut])
        text = text[i:]
    r.append(text)
    return '\n'.join(r)


def get_book_data(isbn: int):
    """Attempt to get book data via the ISBN from the DB, if that fails,
        try the DNB (https://portal.dnb.de)"""
    try:
        book = next(iter(core.Book.search(('isbn', 'eq', isbn))))
    except StopIteration:
        pass  # actually, I could put the whole rest of the function here
    else:
        data = core.Book.view_str(book.id)
        del data['id'], data['status'], data['return_date'], data['borrowed_by']
        del data['borrowed_by_id'], data['__str__']
        return data

    try:
        r = requests.get('https://portal.dnb.de/opac.htm?query=isbn%3D'
                         + str(isbn) + '&method=simpleSearch&cqlMode=true')
        r.raise_for_status()
    except requests.exceptions.RequestException:
        raise core.BuchSchlossError('no_connection', 'no_connection')

    person_re = re.compile(r'(\w*, \w*) \((\w*)\)')
    results = {'concerned_people': []}

    page = bs4.BeautifulSoup(r.text)
    table = page.select_one('#fullRecordTable')
    if table is None:
        # see if we got multiple results
        link_to_first = page.select_one('#recordLink_0')
        if link_to_first is None:
            raise core.BuchSchlossError(
                'Book_not_found', 'Book_with_ISBN_{}_not_in_DNB', isbn)
        r = requests.get('https://portal.dnb.de' + link_to_first['href'])
        page = bs4.BeautifulSoup(r.text)
        table = page.select_one('#fullRecordTable')

    for tr in table.select('tr'):
        td = [x.get_text('\n').strip() for x in tr.select('td')]
        if len(td) == 2:
            if td[0] == 'Titel':
                results['title'] = td[1].split('/')[0].strip()
            elif td[0] == 'Person(en)':
                for p in td[1].split('\n'):
                    g = person_re.search(p)
                    if g is None:
                        continue
                    g = g.groups()
                    if g[1] == 'Verfasser':
                        results['author'] = g[0]
                    else:
                        results['concerned_people'].append(g[1] + ': ' + g[0])
            elif td[0] == 'Verlag':
                results['publisher'] = td[1].split(':')[1].strip()
            elif td[0] == 'Zeitliche Einordnung':
                results['year'] = td[1].split(':')[1].strip()
            elif td[0] == 'Sprache(n)':
                results['language'] = td[1].split(',')[0].split()[0].strip()

    results['concerned_people'] = '; '.join(results['concerned_people'])
    return results


def run():
    """handling function."""
    for k in config.utils.tasks.startup:
        threading.Thread(target=globals()[k], daemon=True).start()
    threading.Thread(target=run_checks, daemon=True).start()


def _default_late_handler(late, warn):
    head = datetime.now().strftime(config.core.date_format).join(('\n\n',))
    with open('late.txt', 'w') as f:
        f.write(head)
        f.write('\n'.join(str(L) for L in late))
    with open('warn.txt', 'w') as f:
        f.write(head)
        f.write('\n'.join(str(w) for w in warn))


late_handlers = [_default_late_handler]
stuff_to_do = [globals()[k] for k in config.utils.tasks.recurring]
