"""Utilities. Mostly periodic checks. Everything that is neither core nor gui

contents (for use):
    - run() -- call once on startup. takes care of all automatic tasks
    - send_mailgun() -- send an email
    - get_name() -- get a pretty name
    - get_book_data() -- attempt to get data about a book based on the ISBN (first local DB, then DNB).

to add late handlers, append them to late_handlers. they will receive arguments as specified in late_books()"""

from datetime import datetime, timedelta, date
import time
import threading
import shutil
import os
import ftplib
import ftputil
import requests
import re
import bs4
import string

from buchschloss import core, config


class FormattedDate(date):
    """print a datetime.date as specified in config.DATE_FORMAT"""
    def __str__(self):
        return self.strftime(config.DATE_FORMAT)

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
        if datetime.now() > core.misc_data.check_date+timedelta(minutes=45):
            for stuff in stuff_to_do:
                threading.Thread(target=stuff).start()
            core.misc_data.check_date = datetime.now() + config.bgtasks_every
        time.sleep(5*60*60)


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
            'and', ('return_date', 'gt', today+config.warn_time))):
        if b.return_date < today:
            late.append(b)
        else:
            warn.append(b)
    for h in late_handlers:
        h(late, warn)


def backup():
    """Local backups.

    Run backup_shift and copy name.ext db to name1.ext"""
    backup_shift(os)
    while True:
        try:
            shutil.copyfile('.'.join(config.DATABASE_NAME),
                            '1.'.join(config.DATABASE_NAME))
        except FileNotFoundError:
            pass
        except PermissionError:  # currently accessing db
            time.sleep(0.5)
            continue
        break


def web_backup():
    """Remote backups.

    Run backup_shift and upload name.ext db as name1.ext
    """
    # noinspection PyDeprecation
    with ftputil.FTPHost(*config.ftp, session_factory=ftplib.FTP_TLS) as host:
        backup_shift(host)
        host.upload('.'.join(config.DATABASE_NAME), '1.'.join(config.DATABASE_NAME))


def backup_shift(fs):
    """shift all nameX.ext up one number to config.backup_depth
    in the given filesystem (os or remote FTP host)"""
    try:
        fs.remove(('%i.' % config.backup_depth).join(config.DATABASE_NAME))
    except FileNotFoundError:
        pass
    for f in range(config.backup_depth, 1, -1):
        try:
            fs.rename(('%i.' % (f-1,)).join(config.DATABASE_NAME),
                      ('%i.' % (f,)).join(config.DATABASE_NAME))
        except FileNotFoundError:
            pass


def send_mailgun(subject, text, to=''):
    """Send an Email using mailgun"""
    recipients = config.implicit_recipients.copy()
    if to:
        recipients.append(to)
    return requests.post(
        config.email_endpoint,
        auth=('api', config.email_auth),
        data={'from': config.email_from,
              'to': recipients,
              'subject': subject,
              'text': text})


def get_name(internal: str):
    """Get the pretty name.

    Try lookup in config.NAMES, else capitalize and replace "_" with " "
    "__" are replaced with ": " and components are converted individually
    """
    if '__' in internal:
        return ': '.join(get_name(s) for s in internal.split('__'))
    return config.NAMES.get(internal, internal.capitalize().replace('_', ' '))


def get_level(n: int = None):
    """Get the representation of the given level. If None is given, use the logged in Member's one."""
    if n is None:
        return config.MEMBER_LEVELS[core.current_login.level]
    else:
        return config.MEMBER_LEVELS[n]


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
            i = size-1
        i += 1
        r.append(text[:i-cut])
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
        r = requests.get('https://portal.dnb.de'+link_to_first['href'])
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
                        results['concerned_people'].append(g[1]+': '+g[0])
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
    for k in config.onstart:
        threading.Thread(target=globals()[k], daemon=True).start()
    threading.Thread(target=run_checks, daemon=True).start()


def _default_late_handler(late, warn):
    head = datetime.now().strftime(config.DATE_FORMAT).join(('\n\n',))
    with open('late.txt', 'w') as f:
        f.write(head)
        f.write('\n'.join(str(L) for L in late))
    with open('warn.txt',  'w') as f:
        f.write(head)
        f.write('\n'.join(str(w) for w in warn))


late_handlers = [_default_late_handler]
stuff_to_do = [globals()[k] for k in config.tasks]
