"""Core functionalities of the application.

Handles access to the database and provides high-level interfaces for all operations.
__all__ exports:
    - BuchSchlossBaseError: the error raised in this module. Comes with a nice description of what exactly failed.
    - DummyErrorFile: a dummy error file (for sys.stderr) that writes errors to log
        and provides access to them e.g. for display or ending
    - misc_data: provide easy access to data stored in Misc by attribute lookup
    - (as of now not, decision pending) Person, Book, Member, Misc: DB model classes for direct usage
    - login, logout: to log  user in or out
    - new_*, edit_*, view_*: interfaces for creating, editing or viewing data
    - activate_group: group activation
    - change_password: Member password change by lvl 4 or member themselves
    - borrow, restitute: "return" is keyword
    - search, ComplexSearch: for searching models
"""

from hashlib import pbkdf2_hmac
from functools import wraps, reduce, partial
from datetime import datetime, timedelta, date
from os import urandom
import warnings
import operator
# noinspection PyPep8Naming
import typing as T
import numbers
import re
import builtins
import traceback
import logging
import peewee

from . import config
from . import utils
from . import models

__all__ = [
    'BuchSchlossBaseError', 'DummyErrorFile', 'misc_data',

    # 'Person', 'Book', 'Member', 'Misc',

    'login', 'logout',

    'new_person', 'new_book', 'new_library', 'new_group', 'new_member',
    'edit_person', 'edit_book', 'edit_library', 'edit_group', 'edit_member',
    'change_password', 'activate_group',
    'view_book', 'view_person', 'view_member', 'view_borrow',

    'borrow', 'restitute',
    'search', 'ComplexSearch',
]

logging.basicConfig(level=logging.INFO,
                    format='{asctime} - {levelname} - {funcName}: {msg}',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    style='{',
                    filename='buchschloss.log'
                    )


def _moved_to(name, dest):
    def deprecated_func(*args, **kwargs):
        warnings.warn('{} has been moved to {}'.format(name, dest.__qualname__),
                      PendingDeprecationWarning)
        return dest(*args, **kwargs)

    deprecated_func.__doc__ = 'moved to {}'.format(dest.__qualname__)
    return deprecated_func


class MiscData:
    """Provide an easy interface for the Misc table."""
    def __getattr__(self, item):
        try:
            conn = models.db.connect(True)
            try:
                return models.Misc.get_by_id(item).data
            finally:
                if conn:
                    models.db.close()
        except models.Misc.DoesNotExist as e:
            raise AttributeError('%s has no attribute %s' % (repr(self), item)) from e

    def __setattr__(self, key, value):
        conn = models.db.connect(True)
        try:
            m = models.Misc.get_by_id(key)
        except models.Misc.DoesNotExist as e:
            raise AttributeError('Can only set database columns, not %s' % (key,)) from e
        else:
            m.data = value
            m.save()
        finally:
            if conn:
                models.db.close()


class BuchSchlossBaseError(Exception):
    """Error raised in this module"""
    def __init__(self, title, message, *sink):
        if sink:
            warnings.warn('BuchSchlossBaseError.__init__ got unexpected arguments')
        self.title = title
        self.message = message

    @classmethod
    def template_title(cls, template_title):
        """return a subclass that will %-format the given template title
            with the one given at creation

            *args are passed along, making this work well with BuchSchlossError
        """
        class BuchSchlossTemplateTitleError(cls):
            def __init__(self, title, message, *args):
                super().__init__(template_title % title, message, *args)
        return BuchSchlossTemplateTitleError

    @classmethod
    def template_message(cls, template_message):
        """return a subclass that will %-format the given template message
            with the one given at creation

            *args are passed, making this work well with BuchSchlossError
        """
        class BuchSchlossTemplateMessageError(cls):
            def __init__(self, title, message, *args):
                super().__init__(title, template_message % message, *args)
        return BuchSchlossTemplateMessageError


class BuchSchlossError(BuchSchlossBaseError):
    """a subclass that will use utils.get_name

        The title will be passed through utils.get_name normally

        The message will be passed through utils.get_name and .format will
        be called with an optional tuple (unpacked) given
    """
    def __init__(self, title, message, *message_format):
        super().__init__(utils.get_name(title),
                         utils.get_name(message).format(*message_format))


BuchSchlossPermError = partial(BuchSchlossError.template_message('must_be_%s'),
                               'no_permission')
BuchSchlossDataMissingError = partial(BuchSchlossError, message='data_missing')


class BuchSchlossNotFoundError(BuchSchlossError.template_title('%s_not_found')
                               .template_message('no_%s_with_id_{}')):
    def __init__(self, model, pk):
        super().__init__(model, model, pk)


class Dummy:  # TODO: move this out to misc
    """Provide a dummy object

    special attributes:
        _default: a default item to be returned when the requested one is not set
        _str: the string representation of self
        _call: a callable to call (default: return self)"""
    def __init__(self, _bool=True, _call=lambda s, *a, **kw: s, **kwargs):
        """Set the attributes given in kwargs."""
        self._bool = _bool
        self._call = _call
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __str__(self):
        """return self._str if set, else '-----'"""
        try:
            return self._str
        except AttributeError:
            return '-----'

    def __call__(self, *args, **kwargs):
        return self._call(self, *args, **kwargs)

    def __bool__(self):
        return self._bool

    def __getattr__(self, item):
        """return self._default if set, else self"""
        if item in ['_default', '_str', '_bool', '_call']:
            try:
                return self.__dict__[item]
            except KeyError as e:
                raise AttributeError from e
        try:
            return self._default
        except AttributeError:
            return self


class DummyErrorFile:
    """Revert errors to log.

    Attributes:
        error_happened: True if write() was called
        error_file: the log file name
        error_texts: list of the error messages wrote to the log file for later use (display, email, ...)"""
    def __init__(self, error_file='error.log'):
        self.error_happened = False
        self.error_texts = []
        self.error_file = 'error.log'
        with open(error_file, 'a', encoding='UTF-8') as f:
            f.write('\n\nSTART: '+str(datetime.now())+'\n')

    def write(self, msg):
        self.error_happened = True
        self.error_texts.append(msg)
        while True:
            try:
                with open(self.error_file, 'a', encoding='UTF-8') as f:
                    f.write(msg)
            except OSError:
                pass
            else:
                break


def pbkdf(pw, salt, iterations=config.HASH_ITERATIONS[0]):
    """return pbkdf2_hmac('sha256', pw, salt, iterations)"""
    return pbkdf2_hmac('sha256', pw, salt, iterations)


def from_db(*arguments: T.Type[models.Model]):
    """Wrap functions taking IDs of database objects.

    convert all arguments at their given position to wrapper_arg.get_by_id(func_arg)
    ignore wrapper arguments of None
    raise a BuchSchlossBaseError with an explainaition if the object does not exist"""
    def wrapper_maker(f):
        @wraps(f)
        def wrapper(*args: T.Any, **kwargs):
            args = list(args)
            with models.db:
                for p, m in enumerate(arguments):
                    try:
                        arg = args[p]
                    except IndexError:
                        raise TypeError('{!r} missing a positional parameter'.format(f))
                    if m is not None and not isinstance(arg, m):  # allow direct passing
                        try:
                            args[p] = m.get_by_id(arg)
                        except m.DoesNotExist:
                            raise BuchSchlossNotFoundError(m.__name__, arg)
            with models.db.atomic():
                return f(*args, **kwargs)
        return wrapper
    return wrapper_maker


def level_required(level):
    """require the given level for executing the wrapped function.
    raise a BuchSchlossBaseError when requirement not met."""
    def wrapper_maker(f):
        @wraps(f)
        def level_required_wrapper(*args, **kwargs):
            if current_login.level >= level:
                return f(*args, **kwargs)
            logging.info('access to {} denied to {}'
                         .format(f.__name__, current_login))
            raise BuchSchlossPermError('must_be_level_{}', utils.get_level(level))
        return level_required_wrapper
    return wrapper_maker


def auth_required(f):
    """require the currently logged member's password for executing the funcion
    raise a BuchSchlossBaseError if not given or wrong"""
    @wraps(f)
    def auth_required_wrapper(*args, current_password: str, **kwargs):
        if authenticate(current_login, current_password):
            logging.info('{} passed authentication for {}'.format(
                current_login, f.__name__))
            return f(*args, **kwargs)
        else:
            logging.info('{} failed to authenticate for {}'.format(
                current_login, f.__name__))
            raise BuchSchlossError('auth_failed', 'wrong_password_for_{}', current_login)

    auth_required_wrapper.__doc__ += (
        '\n\nThis function requires authentication in form of\n'
        'a `current_password` argument containing the currently\n'
        "logged in member's password\n")
    auth_required.functions.append(f.__name__)
    return auth_required_wrapper
auth_required.functions = []


def _try_set_lib(b: models.Book, lib: str, e: set = Dummy(add=lambda x: 0)):
    try:
        b.library = models.Library.get(models.Library.name == lib)
    except models.Library.DoesNotExist:
        e.add(BuchSchlossNotFoundError('Library', lib).message)


def _get_query_arg(e: peewee.DoesNotExist, throw=True):
    try:
        return re.search(r'\[(.*), 1, 0\]$', str(e)).group(1)
    except AttributeError:
        traceback.print_exc()
        if throw:
            raise BuchSchlossError('error', 'error_while_getting_error_msg')


def authenticate(m, password):
    """Check if the given password corresponds to the hashed one.
    Update the hash if newer iteration number present"""
    password = password.encode()
    for old, iterations in enumerate(config.HASH_ITERATIONS):
        if m.password == pbkdf(password, m.salt, iterations):
            if old:
                close_db = models.db.connect(reuse_if_open=True)
                m.password = pbkdf(password, m.salt)
                m.save()
                if close_db:
                    models.db.close()
            return True
    return False


def login(name: str, password: str):
    """attempt to login the Member with the given name and password.

    Try all iterations specified in config.HASH_ITERATIONS
        and update to newest (first) one where applicable
    raise a BuchSchlossBaseError on failure"""
    global current_login
    try:
        with models.db:
            m = models.Member.get_by_id(name)
    except models.Member.DoesNotExist:
        raise BuchSchlossError('login', 'no_Member_with_id_{}', name)
    if authenticate(m, password):
        logging.info('login success {}'.format(m))
        current_login = m
    else:
        logging.info('login fail {}'.format(m))
        raise BuchSchlossError('login', 'wrong_password')


def logout():
    """log the currently logged in Member out"""
    global current_login
    logging.info('logout {}'.format(current_login))
    current_login = dummy_member


get_level = _moved_to('get_level', utils.get_level)


class Book:
    """Namespace for Book-related functions"""

    @staticmethod
    @level_required(2)
    def new(isbn: int, year: int, groups: T.Iterable[str] = (),
            library: str = 'main', **kwargs: str) -> int:
        """Attempt to create a new Book with the given arguments and return the ID

        automatically create groups as needed
        raise a BuchSchlossBaseError on failure

        See models.Book.__doc__ for details on arguments"""
        with models.db:
            try:
                b = models.Book.create(isbn=isbn, year=year,
                                       library=models.Library.get_by_id(library),
                                       **kwargs)
                for g in groups:
                    b.groups.add(models.Group.get_or_create(name=g)[0])
            except models.Library.DoesNotExist:
                raise BuchSchlossNotFoundError('Book', library)
            except peewee.IntegrityError as e:
                if str(e).startswith('NOT NULL'):
                    raise BuchSchlossDataMissingError('new_book')
                else:
                    raise
            else:
                logging.info('{} created {}'.format(current_login, b))
        return b.id

    @staticmethod
    @from_db(models.Book)
    @level_required(2)
    def edit(book: T.Union[int, models.Book], **kwargs):
        """Edit a Book based on the arguments given.

        See Book.__doc__ for more information on the arguments
        raise a BuchSchlossBaseError if the Book isn't found.
        """
        errors = set()
        groups = set(kwargs.pop('groups', ()))
        if all(groups):
            errors.update(_update_library_group(book, 'groups', groups))
        lib = kwargs.pop('library', None)
        if lib is not None:
            _try_set_lib(book, lib, errors)
        for k, v in kwargs.items():
            if isinstance(v, str) and not isinstance(getattr(models.Book, k), peewee.CharField):
                logging.warning('auto-type-conversion used')
                v = type(getattr(book, k))(v)
            setattr(book, k, v)
        book.save()
        logging.info('{} edited {}'.format(current_login, book))
        return errors

    @staticmethod
    @from_db(models.Book)
    def view_str(book: models.Book):
        """Return data about a Book.

        Return a dictionary consisting of the following items as strings:
            - contents of config.BOOK_DATA and id and library attributes
            - groups as a string consisting of group names separated by ';'
            - the book's status (available, borrowed or inactive)
            - return_date either '-----' or the date the book will be returned
            - borrowed_by: '-----' or a representation of the borrowing Person
            - __str__: the string representation of the Book
        and 'borrowed_by_id', the ID of the Person that borrowed the Book
        """
        r = {k: str(getattr(book, k) or '') for k in
             config.BOOK_DATA + ['id', 'library', 'shelf']}
        r['groups'] = ';'.join(g.name for g in book.groups)
        borrow = book.borrow or Dummy(id=None, _bool=False)
        r['status'] = utils.get_name('borrowed' if borrow else
                                     ('available' if book.is_active
                                      else 'inactive'))
        r['return_date'] = borrow.return_date.strftime(config.DATE_FORMAT)
        r['borrowed_by'] = str(borrow.person)
        r['borrowed_by_id'] = borrow.person.id
        r['__str__'] = str(book)
        logging.info('{} viewed {}'.format(current_login, book))
        return r

    @staticmethod
    @from_db(models.Book)
    def view_ns(book):
        """Return data about a Book.

        Return a Python object with the following attributes:
            - isbn: int
            - author, title language, publisher, medium, shelf: str
            - series, concerned_peoplem genres: str or None
            - year: int
            - library: models.Library
            - is_active: bool
            - borrow: object as returned by Borrow.view_ns or None

        Actually, the returned object is instance of models.Book,
        but this may change if I ever decide to use something else for
        data storage
        """
        return book


class Person:
    """Namespace for Person-related functions"""
    @staticmethod
    @level_required(3)
    def new(id_: int, first_name: str, last_name: str, class_: str,
            max_borrow: int = 3, libraries: T.Iterable[str] = ('main',),
            pay: bool = None, pay_date: date = None):
        """Attempt to create a new Person with the given arguments.

        raise a BuchSchlossBaseError on failure.

        See Person for details on arguments
        If ``pay`` is True and ``pay_date`` is None,
            set the pay_date to ``datetime.date.today()``
        """
        if pay_date is None and pay:
            pay_date = date.today()
        if max_borrow > 3 and not current_login.level >= 4:
            raise BuchSchlossPermError(utils.get_level(4))
        p = models.Person(id=id_, first_name=first_name, last_name=last_name,
                          class_=class_, max_borrow=max_borrow, pay_date=pay_date)
        try:
            with models.db:
                for lib in libraries:
                    p.libraries.add(models.Library.get(models.Library.name == lib))
                p.save(force_insert=True)
        except models.Library.DoesNotExist as e:
            raise BuchSchlossNotFoundError('Library', _get_query_arg(e))
        except peewee.IntegrityError as e:
            traceback.print_exc()
            if str(e).startswith('UNIQUE'):
                raise BuchSchlossError('Person', 'id_{}_for_Person_already_used', id_)
            elif str(e).startswith('NOT NULL'):
                raise BuchSchlossDataMissingError('new_person')
            else:
                raise
        else:
            logging.info('{} created {} with pay={}'.format(current_login, p, pay))

    @staticmethod
    @level_required(3)
    @from_db(models.Person)
    def edit(person: T.Union[int, models.Person], **kwargs):
        """Edit a Person based on the arguments given.

        See Person.__doc__ for more information on the arguments
        `pay` may be passed as argument with a truthy model to set
            `pay_date` to `datetime.date.today()`

        raise a BuchSchlossBaseError if the Person isn't found.
        Return a set of errors found during updating the person's libraries
        """
        if kwargs.pop('pay', False):
            kwargs['pay_date'] = date.today()
        errors = set()
        lib = set(kwargs.pop('libraries', ()))
        if all(lib):
            errors.update(_update_library_group(person, 'libraries', lib))
        for k, v in kwargs.items():
            setattr(person, k, v)
        person.save()
        logging.info('{} edited {}'.format(current_login, person)
                     + (' setting pay_date to {}'.format(kwargs['pay_date'])
                        if 'pay_date' in kwargs else ''))
        return errors

    @staticmethod
    @level_required(1)
    @from_db(models.Person)
    def view_str(person: models.Person):
        """Return data about a Person.

        Return a dict consisting of the following items as strings:
            - id, first_name, last_name, class_ max_borrow, pay_date attributes
            - libraries as a string, individual libraries separated by ;
            - borrows as a tuple of strings;
            - __str__ , the string representation
        and 'borrow_book_ids', a sequence of the IDs of the borrowed books
            in the same order their representations appear in 'borrows'"""
        r = {k: str(getattr(person, k) or '') for k in
             'id first_name last_name class_ max_borrow pay_date'.split()}
        borrows = search(models.Borrow, (('person', 'eq', person.id),
                                         'and', ('is_back', 'eq', False)))
        r['borrows'] = tuple(map(str, borrows))
        r['borrow_book_ids'] = [b.book.id for b in borrows]
        r['libraries'] = ';'.join(L.name for L in person.libraries)
        r['__str__'] = str(person)
        logging.info('{} viewed {}'.format(current_login, person))
        return r

    @staticmethod
    @from_db(models.Person)
    def view_ns(person):
        """Return data about a Person.

        Return a Python object with the following attributes:
            - id, max_borrow: int
            - first_name, last_name, class_: str
            - pay_date: datetime.date or None
            - libraries: iterable of objects as returned by Library.view_ns
                representing the Person's libraries
            - borrows: iterable of objects as returned by Borrow.view_ns
                representing the Person's borrows

        Actually, the returned object is instance of models.Person,
        but this may change if I ever decide to use something else for
        data storage
        """
        return person


class Library:
    """Namespace for Library-related functions"""
    @staticmethod
    @level_required(3)
    def new(name: str, books: T.Iterable[int],
            people: T.Iterable[int], pay_required: bool = True):
        """Create a new Library with the specified name and add it to the specified
                people and books.

            ``people`` and ``books`` are iterables of the IDs of the poeple and books
                to gain access / be transferred to the new library
            if a Library with the given name already exists, add it to the given
                people and books
            return a set of strings describing any encountered errors
        """
        return new_library_group('library', name, books, people, pay_required, True)


def new_person(id: int, *args, **kwargs):
    """moved to Person.new"""
    warnings.warn('new_person has been moved to Person.new', PendingDeprecationWarning)
    return Person.new(id, *args, **kwargs)


new_book = _moved_to('new_book', Book.new)
new_library = _moved_to('new_library', Library.new)


def new_group(name: str, books: T.Iterable[int]):
    """Create a new Group with the specified name and add the given books to it

        ``books`` is an iterable of the IDs of the books to be added
        return a set of strings describing encountered errors
    """
    return new_library_group(name, books, _is_internal_call=True)


@level_required(3)
def new_library_group(what: T.Union[T.Type[models.Library], T.Type[models.Group]],
                      name: str,
                      books: T.Iterable[int],
                      people: T.Iterable[int] = (),
                      pay_required: bool = True,
                      _is_internal_call=False,
                      _skip_library=False,
                      ):
    """deprecated"""
    # these two allow legacy calls specifying 'library' or 'group' at
    # first position or as ``what``. Can be removed once nobody uses them.
    if isinstance(what, str):
        what = {'library': models.Library, 'group': models.Group}[what]
    if not _is_internal_call:
        warnings.warn('use {}.new instead of new_library_group'.format(what.capitalize()),
                      DeprecationWarning)
    # ``lib`` is a Library or a Group
    lib, new = what.get_or_create(name=name)
    errors = set()
    with models.db:
        for b in books:
            try:
                b = models.Book.get_by_id(b)
            except models.Book.DoesNotExist:
                errors.add(BuchSchlossNotFoundError('Book', b).message)
            else:
                if what == 'library':
                    _try_set_lib(b, name, errors)
                elif what == 'group':
                    try:
                        b.groups.add(lib)
                    except peewee.IntegrityError as e:
                        if str(e).startswith('UNIQUE'):
                            errors.add(utils.get_name('Book_{}_in_Group_{}').format(b.id, name))
                        else:
                            raise
                    b.save()
    logging.info('{} created {}'.format(current_login, lib))
    if _skip_library or what == 'group':
        return errors  # only libraries for people
    with models.db:
        for p in people:
            try:
                p = models.Person.get_by_id(p)
            except models.Person.DoesNotExist:
                errors.add(BuchSchlossNotFoundError('Person', p).message)
            else:
                if what == 'library':
                    try:
                        p.libraries.add(lib)
                    except peewee.IntegrityError as e:
                        if str(e).startswith('UNIQUE'):
                            errors.add('Person_{}_in_Library_{}'.format(p, name))
                p.save()
    lib.pay_required = pay_required
    lib.save()
    return errors


@auth_required
@level_required(4)
def new_member(name: str, password: str, level: int):
    """Create a new Member with the specified properties.

    A salt of the length specified in config.HASH_SALT_LENGTH
        is randomly generated and used to hash the password.
    See the wrapping pbkdf function in this module for hashing details
    """
    salt = urandom(config.HASH_SALT_LENGTH)
    pass_hash = pbkdf(password.encode('UTF-8'), salt)
    try:
        with models.db:
            m = models.Member.create(name=name, password=pass_hash, salt=salt, level=level)
    except peewee.IntegrityError as e:
        if str(e).startswith('UNIQUE'):
            raise BuchSchlossError('Member', 'id_{}_for_Member_already_used', name)
        else:
            raise
    logging.info('{} created {}'.format(current_login, m))


edit_person = _moved_to('edit_person', Person.edit)
edit_book = _moved_to('edit_book', Book.edit)


def _update_library_group(o: models.Model, what: str, new: T.Set[str]):
    libgr = getattr(o, what)
    errors = set()
    old = set(lg.name for lg in libgr)
    lg_model = libgr.rel_model
    for add in new.difference(old):
        try:
            libgr.add(lg_model.get(name=add))
        except lg_model.DoesNotExist:
            errors.add(BuchSchlossNotFoundError(lg_model, add).message)
    for rem in old.difference(new):
        # these are the ones we just read from the database,
        # if we get an error here it's bad, so let it crash
        libgr.remove(lg_model.get(name=rem))
    return errors


def edit_library(action: str, name: str, people: T.Iterable[int] = (),
                 books: T.Iterable[int] = (), pay_required: bool = None) -> set:
    """Perform the given action on the Library with the given name

        'delete' will remove the reference to the library from all given people
            and books (setting their library to 'main'),
            but not actually delete the Library itself
            ``people`` and ``books`` are ignored in this case
        'add' will add the Library to all given people and set the library
            of all the given books to the specified one
        'remove' will remove the reference to the given Library in the given people
            and set the library of the given books to 'main'

        ``name`` is the name of the Library to modify
        ``people`` is an iterable of the IDs of the people to modify
        ``books`` is an iterable of IDs of the books to modify
        ``pay_required`` will set the Library's payment requirement to itself if not None

        return a set of strings describing encountered errors
    """
    return edit_library_group('library', action, name, people, books,
                              pay_required, True)


def edit_group(action: str, name: str, books: T.Iterable[int]) -> set:
    """Perform the given action on the specified Group

        'delete' will remove the reference to the grou from all given books,
            but not actually delete the Group itself
            ``books`` is ignored in this case
        'add' will add the Group to all given books
        'remove' will remove the reference to the given Group in the given books

        ``name`` is the name of the Group to modify
        ``books`` is an iterable of the IDs of the books to modify

        return a set of strings describing encountered errors
    """
    return edit_library_group('group', action, name, books, _is_internal_call=True)


@level_required(3)
def edit_library_group(what: str, action: str, name: str,
                       people: T.Iterable[int] = (),
                       books: T.Iterable[int] = (),
                       pay_required: bool = None,
                       _is_internal_call=False) -> set:
    """Perform action on the group or library `name`.

    `what` is either 'library' or 'group'.
    if action is 'delete', remove name from all references in books (and people)
        but don't actually delete the library/group
    if action is 'add', add name to references to what in given books (and people)
        remain silent when requested to add books/people to a library/group they already belong to
    if action is 'remove', remove name from references in given books (and people)
    return a list of error messages if any errors were encountered

    detail: if `what` is neither 'library' nor 'group', a KeyError is raised"""
    if not _is_internal_call:
        logging.warning('edit_library_group called directly')
    # attention -- lib is a Group of Library object, depending on context
    try:
        lib = {'library': models.Library, 'group': models.Group}[what].get_by_id(name)
    except models.Library.DoesNotExist:
        raise BuchSchlossNotFoundError('Library', name)
    except models.Group.DoesNotExist:
        raise BuchSchlossNotFoundError('Group', name)

    errors = set()
    if action == 'delete':
        with models.db:
            if what == 'library':
                for p in models.Person.select().join(models.Person.libraries.through_model).join(
                        models.Library).where(models.Library.name == name):
                    p.libraries.remove(lib)
                    p.save()
                for b in models.Book.filter(models.Book.library == lib):
                    _try_set_lib(b, 'main', errors)
                    b.save()
            elif what == 'group':
                for b in (models.Book.select().join(models.Book.groups.through_model).join(models.Group)
                          .where(models.Group.name == name)):
                    b.groups.remove(lib)
                    # b.save()
        return errors

    if what == 'library':
        for s_nr in people:
            with models.db:
                try:
                    p = models.Person.get_by_id(s_nr)
                except models.Person.DoesNotExist:
                    errors.add(BuchSchlossNotFoundError('Person', s_nr).message)
                else:
                    if action == 'add' and lib not in p.libraries:
                        p.libraries.add(lib)
                    elif action == 'remove':
                        p.libraries.remove(lib)
                    p.save()
    for b_id in books:
        with models.db:
            try:
                b = models.Book.get_by_id(b_id)
            except models.Book.DoesNotExist:
                errors.add(BuchSchlossNotFoundError('Book', b_id))
            else:
                if action == 'add':
                    if what == 'library':
                        _try_set_lib(b, name, errors)
                    elif what == 'group' and lib not in b.groups:
                        b.groups.add(lib)
                elif action == 'remove':
                    if what == 'library':
                        if b.library.name != name:
                            errors.add(utils.get_name('Book_not_in_Library_{}')
                                       .format(name))
                        else:
                            _try_set_lib(b, 'main', errors)
                    elif what == 'group':
                        b.groups.remove(lib)
                b.save()
    if pay_required is not None and what == 'library':
        lib.pay_required = pay_required
        lib.save()
    logging.info('{} edited {}, involving People: {} and Books: {}'
                 .format(current_login, lib, people, books))
    return errors


@auth_required
@level_required(4)
@from_db(models.Member)
def edit_member(m: models.Member, **kwargs):
    """Edit a member.

    Set the attributes of the Member object retrieved to the arguments passed.
    wrapper raises BuchSchlossBaseError on failure"""
    old = str(m)
    for k, v in kwargs.items():
        setattr(m, k, v)
    logging.info('{} edited {} to {}'.format(current_login, old, m))
    m.save()


@auth_required
@from_db(models.Member)
def change_password(m: models.Member, new_password: str):
    """Change a Member's password and use a new salt

    new_password is the new password of the Member being edited
    Editing requires being level 4 or the editee
    If the editee is currently logged in, update"""
    global current_login
    if current_login.level < 4 and current_login.name != m.name:
        raise BuchSchlossError('no_permission', 'no_edit_password_permission')
    m.salt = urandom(config.HASH_SALT_LENGTH)
    m.password = pbkdf(new_password.encode('UTF-8'), m.salt)
    m.save()
    if current_login.name == m.name:
        current_login = m
    logging.info("{} changed {}'s password".format(current_login, m))


@level_required(3)
def activate_group(name: str, src: T.Iterable[str] = (), dest: str = ''):
    """Activate a group.

    name is the group name
    src is an iterable of origin libraries
    dest is the target library
    if src is a falsely model (empty), the origin is all libraries
    if dest is a falsely model, the destination is 'main'

    return a set of strings describing encountered errors or the number of moved books"""
    errors = set()
    with models.db:
        if not tuple(models.Group.select(models.Group.name).where(models.Group.name == name)):
            return {utils.get_name('no_group_{}').format(name)}
        for b in models.Book.select().join(
                models.Book.groups.through_model).join(
                models.Group).where(models.Group.name == name):
            if not src or b.library.name in src:
                _try_set_lib(b, dest or 'main', errors)
                b.save()
    logging.info('{} activated {!r}'.format(current_login, name))
    return errors


view_person = _moved_to('new_person', Person.view_str)
view_book = _moved_to('new_book', Book.view_str)


@level_required(1)
@from_db(models.Member)
def view_member(member: models.Member):
    """Return information about a member

    Return a dictionary with the member's name and level"""
    return {'name': member.name, 'level': member.level}


@level_required(1)
@from_db(models.Borrow)
def view_borrow(borrow: models.Borrow):
    """Return information about a borrow action

    Return a dictionary with the following items as strings:
        - 'person': a string representation of the borrowing Person
        - 'person_id': the ID (id) of the borrowing Person
        - 'book': a string representation of the borrowed Book
        - 'book_id': the ID of the borrowed Book
        - 'return_date': a string representation of the date
            by which the book has to be returned
        - 'is_back': a boolean indicating if the book has been returned
        - '__str__': a string representation of the Borrow
    """
    r = {k: str(getattr(borrow, k)) for k in ['person', 'book', 'return_date']}
    r.update({
        'person_id': borrow.person.id,
        'book_id': borrow.book.id,
        'is_back': borrow.is_back,
        '__str__': str(borrow),
    })
    return r


# @level_required(1) -- enforced by borrowing times
@from_db(models.Book, models.Person, None)
def borrow(b: models.Book, p: models.Person, weeks: numbers.Real):
    """Borrow a book.

    ``weeks`` is the time to borrow in weeks.

    raise an error if
        a) the Person or Book does not exist
        b) the Person has reached their limit set in max_borrow
        c) the Person is not allowed to access the library the book is in
        d) the Book is not available
        e) the Person has not paid for over 52 weeks and the book's
            Library requires payment
        f) ``weeks`` exceeds the one allowed to the executing member
        g) ``weeks`` is <= 0

    level | max weeks borrowing allowed  TODO: put this somewhere into config
    1     | 5
    2     | 7
    3     | 10
    4     | 20
    """
    if weeks > (0, 5, 7, 10, 20)[current_login.level]:
        raise BuchSchlossError('borrow', 'no_permission_borrow_{}_weeks', weeks)
    if weeks <= 0:
        raise BuchSchlossError('borrow_time', 'borrow_time_negative')
    if b.borrow or not b.is_active:
        raise BuchSchlossBaseError('borrow', '{}_not_available', b.id)
    if b.library not in p.libraries:
        raise BuchSchlossBaseError(
            'no_permission', '{}_may_not_borrow_from_{}', p, b.library)
    if (b.library.pay_required
            and (p.pay_date or date.min) + timedelta(weeks=52) < date.today()):
        raise BuchSchlossBaseError('no_payment', 'no_payment_for_{}', p)
    if models.Borrow.select().where(models.Borrow.person == p, models.Borrow.is_back == False
                                    ).count() >= p.max_borrow:
        raise BuchSchlossBaseError('borrow', '{}_reached_max_borrow', p)
    rdate = datetime.today()+timedelta(weeks=float(weeks))
    models.Borrow.create(return_date=rdate, person=p, book=b)
    logging.info('{} borrowed {} to {} until {}'
                 .format(current_login, b, p, rdate))
    latest = misc_data.latest_borrowers
    # avoid writing intermediary stuff to the DB
    # I'm pretty sure it only does on explicit assignment, but BSTS
    # plus, it saves a bit of typing
    if p.id in latest:
        latest.remove(p.id)
    else:
        latest = latest[:config.no_latest_borrowers_save - 1]
    latest.insert(0, p.id)
    misc_data.latest_borrowers = latest


@level_required(1)
@from_db(models.Book, models.Person)
def restitute(book: models.Book, person: models.Person = None, person_match: bool = True):  # return is keyword
    """Restitute a book.

    raise a BuchSchlossBaseError if:
        a) the book or person doesn't exist OR
        b) the book is not borrowed OR
        c) the person has not borrowed the book and `person_match` is True"""
    borrow = book.borrow
    if borrow is None:
        raise BuchSchlossBaseError('Book_not_borrowed', '{}_not_borrowed', book)
    elif person_match and borrow.person != person:
        raise BuchSchlossBaseError(
            'Book_not_borrowed', '{}_not_borrowed_by_{}', book, person)
    borrow.is_back = True
    borrow.save()
    logging.info('{} confirmed {} returned {}'
                 .format(current_login, person, book))


def search(o: T.Type[models.Model], condition: T.Tuple = None,
           *complex_params: 'ComplexSearch', complex_action: str = 'or',
           _in_=None, _eq_=None):
    """Search for objects.

        `condition` is a tuple of the form (<a>, <op>, <b>)
            with <op> being a logical operation ("and" or "or") and <a>
                and <b> in that case being condition tuples
            or a comparison operation ("contains", "eq", "ne", "gt", "ge",
                "lt" or "le")
                in which case <a> is a (possibly dotted) string corresponding
                to the attribute name and <b> is the model to compare to.
        `complex_params` is a sequence of ComplexSearch instances to apply after
            executing the SQL SELECT
        `complex_action` is "and" or "or" and specifies how to handle multiple
            complex cases. If finer granularity is needed, it can be achieved with
            bitwise operators, providing bools are used.

        Note: for `condition`, there is no "not" available.
            Use the inverse comparision operator instead

        This function is compatible with its predecessor and will forward
            `complex_params`, `_in_`, `_eq_` and `condition` (as `kind` argument)
            to the old function.
    """
    if isinstance(condition, str):
        # call to old function
        # noinspection PyDeprecation
        return _search_old(o, condition, *complex_params, _in_=(_in_ or {}), _eq_=(_eq_ or {}))
    if condition is None:
        # call with default arg
        # noinspection PyDeprecation
        return _search_old(o, _eq_=(_eq_ or {}), _in_=(_in_ or {}))

    def follow_path(path, q):
        def handle_many_to_many():
            through = fv.through_model.alias()
            return q.join(through, on=(getattr(fv.model, fv.model.pk_name)
                                       == getattr(through, fv.model.__name__.lower() + '_id'))
                          ).join(mod, on=(getattr(through, mod.__name__.lower() + '_id')
                                          == getattr(mod, mod.pk_name)))

        *path, end = path.split('.')
        mod = o
        for fn in path:
            fv = getattr(mod, fn)
            mod = fv.rel_model.alias()
            if isinstance(fv, peewee.ManyToManyField):
                q = handle_many_to_many()
            else:
                q = q.join(mod, on=(fv == getattr(mod, mod.pk_name)))
        fv = getattr(mod, end)
        if isinstance(fv, peewee.ManyToManyField):
            mod = fv.rel_model
            q = handle_many_to_many()
            fv = getattr(mod, mod.pk_name)
        return fv, q

    def handle_condition(a, op, b, q):
        if op == 'and':
            return handle_condition(*b, handle_condition(*a, q).switch(o))
        elif op == 'or':
            return handle_condition(*a, q) + handle_condition(*b, q)
        else:
            a, q = follow_path(a, q)
            if op in ('eq', 'ne', 'gt', 'lt', 'ge', 'le'):
                return q.where(getattr(operator, op)(a, b))
            elif op == 'contains':
                return q.where(a.contains(b))
            else:
                raise ValueError('`op` must be "and", "or", "eq", "ne", "gt", "lt" '
                                 '"ge", "le" or "contains"')
    query = o.select(*o.str_fields)
    result = handle_condition(*condition, query)
    if complex_params:
        return do_complex_search(complex_action, result, complex_params)
    else:
        return result


# noinspection PyDefaultArgument
def _search_old(o: T.Type[models.Model], kind: str = 'or', *complex_params, _in_={}, _eq_={}):
    """Search a model's objects.

    `_in_` is a mapping of attribute name to model contained
    `_eq_` is a mapping of attribute name to model equal
    `complex_params` may be instances of ComplexSearch allowing complex queries.

    While `_in_` and `_eq_` are processed at SQL level, the complex parameters
    are handled after having made a query

    The objects returned have enough data to be representable as strings.
    If more data is needed, the appropriate view_* function may be called
    """
    warnings.warn('use the new condition specification in search',
                  DeprecationWarning, stacklevel=2)
    req_level = next(i for i, mods in enumerate(
        ((models.Book,), (models.Person, models.Borrow), (), models.Model.__subclasses__())) if o in mods)
    if req_level > current_login.level:
        raise BuchSchlossBaseError(utils.get_name('no_permission'),
                                   utils.get_name('must_be_{}').format(
                                   get_level(req_level)))

    def add_to_query(q):
        nonlocal query
        if kind == 'and':
            query = q.switch(type(o))
        elif kind == 'or':
            query += q
        else:
            raise ValueError('`kind` must be "and" or "or"')

    def handle_many_to_many(q, f):
        # All I want to do is get the referenced
        # instance. I couldn't find an easier way
        # to do this, but I feel there should be one...
        # there is: .rel_model
        model = next(v_ for k_, v_ in f.through_model._meta.fields.items()
                     if k_ not in  ('id', k)).rel_field.model
        q = q.join(f.through_model).join(model)
        q = q.where(op(model._meta.primary_key, v))
        add_to_query(q)

    # INFO: this is not final
    with models.db:
        query = o.select(*o.str_fields)
    conditions = []
    for mapping, op in ((_in_, peewee.Field.contains), (_eq_, operator.eq)):
        for k, v in mapping.items():
            # django-filter-style, these keys might have been identifiers
            k = k.replace('__', '.')
            if '.' in k:
                *path, end = k.split('.')
                mod = o
                q = query
                for fk in path:
                    mod = getattr(mod, fk).rel_model
                    q = q.join(mod)
                field = getattr(mod, end)
                if isinstance(field, peewee.ManyToManyField):
                    handle_many_to_many(q, field)
                else:
                    add_to_query(q.where(op(field, v)))
            else:
                f = getattr(o, k)
                if isinstance(f, peewee.ManyToManyField):
                    handle_many_to_many(query, f)
                else:
                    conditions.append(op(f, v))
    if conditions:
        query = query.where(reduce(
            {'and': operator.and_, 'or': operator.or_}[kind], conditions))
    if complex_params:
        return do_complex_search(kind, query, complex_params)
    logging.info('{} performed a search for {}'.format(current_login, o))
    return query


def do_complex_search(kind: str, objects: T.Iterable[models.Model], complex_params):
    results = set()
    for o in objects:
        for c in complex_params:
            if c.apply_lookups(o):
                if kind == 'or':
                    results.add(o)
                    break
            elif kind == 'and':
                break
        else:
            if kind == 'and':
                results.add(o)
    return results


def _cs_lookup(name):
    def wrapper(self, other):
        self.lookups.append((name, other))
        return self
    return wrapper


class ComplexSearch:
    """Allow complex lookups and comparisons when using search().

    To later perform attr and/or item lookups on objects when searching,
    perform these lookups in an instance of ComplexSearch.
    e.g.: 'tim' in ComplexSearch().metadata['author'] TODO: update example
    Store attribute and item lookups internally, to actually perform them, call apply_lookups()
    Treat comparisons (== != < <= > >= in) as item lookups

    to use iterations, call iter and perform the operations you would perform
        on the individual items on the return model
    e.g.: [c['y'] for b in a for c in b.x] becomes iter(iter(ComplexSearch()).x)['y']  where `a` is the base instance

    You can call a function on a lookup (or a sequence like above) by accessing the attribute ._call__<name>_
        where name is a key in .CALLABLE_FUNCTIONS that maps to the desired function.
        Currently included by default are `min`, `max`, `all`, `any`, `len` and `sum`
    e.g.: ``any(x in g.name for g in book.groups)`` becomes ``iter(ComplexSearch().groups).name._call__any_``;
          ``sum(x == b.c for b in a) >= 3`` becomes ``(iter(ComplexSearch()).c == x)._call__sum_ >= 3``;
          ``sum(any(a.b in x for a in c) for c in d) in y`` becomes ``(iter(c).b in x)._call__any_._call__sum_ in y``
          bad-looking ~ complexity * use_of_functions ** 3

    Comparisons also work if they are only supported by the known (not simulated) object **IF** the simulated one
        returns NotImplemented in the comparison function
    """
    CALLABLE_FUNCTIONS = {k: getattr(builtins, k) for k in 'min max all any len sum'.split()}

    def __init__(self, return_first_item=True):
        """Initialise self.

        see ComplexSearch.__doc__ for more inforamtion.
        see apply_lookups.__doc__ for information on return_first_item"""
        self.lookups = []
        self.return_first_item = return_first_item

    def __iter__(self):
        self.lookups.append(('__iter__', None))
        return self

    def __next__(self):
        # not really sure what to do here, could also raise TypeError or not include __next__
        raise StopIteration

    #  avoid "attr not found" and "does not support item lookups" warnings
    __getitem__ = _cs_lookup('__getitem__')

    def __getattr__(self, item):
        self.lookups.append(('__getattribute__', item))
        return self

    for op in 'eq ne ge gt le lt contains'.split():
        op = '__%s__' % op
        locals()[op] = _cs_lookup(op)

    def apply_lookups(self, to):
        """Apply the stored lookups to ``to``

        handle __iter__ and _call__<name>_ uses as stated in the class __doc__
        if return_first_item (set in __init__) is True, return only the first item.
            if only one item is expected, this is the way to go"""
        to = [to]
        for k, v in self.lookups:
            m = re.match('_call__(%s)_' % '|'.join(self.CALLABLE_FUNCTIONS.keys()), k)
            if m:
                to = self.CALLABLE_FUNCTIONS[m.group(1)](to if len(to) > 1 else to[0])
            elif k == '__iter__':
                new = []
                for obj in to:
                    for new_obj in iter(obj):
                        new.append(new_obj)
                to = new
            else:
                for i, obj in enumerate(to):
                    new = getattr(obj, k)(v)
                    if new is NotImplemented:
                        new = getattr(v, k)(obj)
                        if new is NotImplemented:
                            raise TypeError('unsupported operation %s between %s and %s'
                                            % (k, obj, v))
                    to[i] = new
        return to[0] if self.return_first_item else to


dummy_member = Dummy(name='<dummy member>', password=b'', salt=b'', level=0)
current_login = dummy_member
misc_data = MiscData()

logging.info('core operational')

