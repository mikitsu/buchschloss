"""model definitions"""
import datetime
import json
import sys
import typing

import peewee
from peewee import (SqliteDatabase, CharField, IntegerField, DateField, BooleanField,
                    BlobField, ForeignKeyField, ManyToManyField, AutoField)
from playhouse.fields import PickleField

try:
    from . import config
except ImportError:
    try:
        import config
    except ImportError:
        config = None
if __name__ != '__main__':
    from . import core

__all__ = [
    'db',
    'Model',
    'Person',
    'Book',
    'Library',
    'Group',
    'Borrow',
    'Member',
    'Misc',
]


T = typing

if config is not None:
    db = SqliteDatabase(config.core.database_name)
else:
    db = SqliteDatabase(input('Unable to locate config module. Please insert DB name -> '))


class JSONField(peewee.TextField):
    """Save JSON objects"""
    def python_value(self, value):
        return None if value is None else json.loads(value)

    def db_value(self, value):
        return None if value is None else json.dumps(value)


class Model(peewee.Model):
    """Base class for all models."""
    DoesNotExist: peewee.DoesNotExist
    str_fields: T.Set[peewee.Field]
    pk_name: str = 'id'
    format_str: str = '<{0.__class__} object -- you should never see this text>'

    class Meta:
        database = db

    @classmethod
    def select_str_fields(cls, extra_fields: set):
        """return cls.select(*<all string fields>)"""
        return cls.select(*(getattr(cls, f) for f in cls.str_fields | extra_fields))

    def __str__(self):
        return self.format_str.format(self)


class ScriptPermissionField(IntegerField):
    def python_value(self, value):
        # noinspection PyArgumentList
        return core.ScriptPermissions(value)

    def db_value(self, value):
        return value.value


class Person(Model):
    """Represent a registered Student

    Repräsentiert einen angemeldeten Schüler

    Attributes:
        - id
        - first_name
        - last_name
        - class_
        - max_borrow: max. number of borrowings allowed simultaneously
        - borrows: current borrows
        - borrow_permission: date until borrowing from restricted libraries is allowed
        - libraries: libraries allowed
    """
    id: T.Union[int, IntegerField] = IntegerField(primary_key=True)
    first_name: T.Union[str, CharField] = CharField()
    last_name: T.Union[str, CharField] = CharField()
    class_: T.Union[str, CharField] = CharField()
    max_borrow: T.Union[int, IntegerField] = IntegerField()
    borrow_permission: T.Union[datetime.date, DateField] = DateField(null=True)
    borrows: peewee.BackrefAccessor
    libraries: T.Union[peewee.ManyToManyQuery, peewee.ManyToManyField]  # libraries as backref

    str_fields = {'id', 'last_name', 'first_name'}
    format_str = 'Person[{0.id}]"{0.last_name}, {0.first_name}"'


class Library(Model):
    """Represent the libraries a Person has access to."""
    people: T.Union[peewee.ManyToManyQuery, peewee.ManyToManyField]\
        = ManyToManyField(Person, 'libraries')
    books: T.Union[peewee.ManyToManyQuery, peewee.ManyToManyField]
    name: T.Union[str, CharField] = CharField(primary_key=True)
    pay_required: T.Union[bool, BooleanField] = BooleanField(default=True)

    format_str = 'Library[{0.name}]'
    str_fields = {'name'}
    pk_name = 'name'


class Book(Model):
    """Represent a Book.

    Attributes (selection):
        - author, isbn, title, series, language, publisher, concerned_people,
            year, medium, genres : general data about the book
        - id [automatically added]: the book ID
        - library: the book's library, determining ho can borrow it
        - groups: the book's groups, for easy library assignment
        - borrow: the book's borrow info
        - is_active [automatically added]: indicate if the book
            is still there (loss, damage, sold...)
    """
    isbn: T.Union[int, IntegerField] = IntegerField()
    author: T.Union[str, CharField] = CharField()
    title: T.Union[str, CharField] = CharField()
    series: T.Union[str, CharField] = CharField(null=True)
    series_number: T.Union[int, IntegerField] = IntegerField(null=True)
    language: T.Union[str, CharField] = CharField()
    publisher: T.Union[str, CharField] = CharField()
    concerned_people: T.Union[str, CharField] = CharField(null=True)
    year: T.Union[int, IntegerField] = IntegerField()
    medium: T.Union[str, CharField] = CharField()

    genres: peewee.BackrefAccessor
    borrow: peewee.BackrefAccessor
    groups: peewee.BackrefAccessor
    id: T.Union[int, IntegerField] = AutoField(primary_key=True)
    library: T.Union[Library, ForeignKeyField] = ForeignKeyField(Library, backref='books')
    shelf: T.Union[str, CharField] = CharField()
    is_active: T.Union[bool, BooleanField] = BooleanField(default=True)

    str_fields = {'id', 'title'}
    format_str = 'Book[{0.id}]"{0.title}"'


class Genre(Model):
    """A single genre-book pair"""
    book = ForeignKeyField(Book, backref='genres')
    name: T.Union[str, CharField] = CharField()

    pk_name = 'name'  # for search

    class Meta:
        primary_key = peewee.CompositeKey('book', 'name')


class Group(Model):
    """Represent a Group."""
    book = ForeignKeyField(Book, backref='groups')
    name: T.Union[str, CharField] = CharField()

    format_str = 'Group[{0.name}]'
    str_fields = {'name'}
    pk_name = 'name'  # for search

    class Meta:
        primary_key = peewee.CompositeKey('book', 'name')


class Borrow(Model):
    """Represent a borrow action.

    Attributes:
        - person: the Person borrowing
        - book: the Book borrowed
        - is_back: if the Book was returned
        - return_date: date by which the Book must de returned
    """
    id: T.Union[int, IntegerField] = AutoField(primary_key=True)
    person: Person = ForeignKeyField(Person, backref='borrows')
    book: Book = ForeignKeyField(Book, backref='borrow')
    is_back: T.Union[bool, BooleanField] = BooleanField(default=False)
    return_date: T.Union[datetime.date, DateField] = DateField()

    str_fields = {'id', 'person', 'book'}
    format_str = 'Borrow[{0.id}]({0.book}, {0.person})'


class Member(Model):
    """Represent a Member of the library organisation team"""
    name: T.Union[str, CharField] = CharField(primary_key=True)
    password: T.Union[bytes, BlobField] = BlobField()
    salt: T.Union[bytes, BlobField] = BlobField()
    level: T.Union[int, IntegerField] = IntegerField()

    format_str = 'Member[{0.name}]({0.level})'
    str_fields = {'name', 'level'}
    pk_name = 'name'


class Script(Model):
    """Represent a lua script"""
    name: T.Union[str, CharField] = CharField(primary_key=True)
    code: T.Union[str, peewee.TextField] = peewee.TextField()
    setlevel: T.Union[int, IntegerField] = IntegerField(null=True)
    storage: T.Union[dict, JSONField] = JSONField()
    permissions: 'T.Union[core.ScriptPermissions, ScriptPermissionField]' \
        = ScriptPermissionField()

    format_str = 'Script[{0.name}]({0.setlevel})'
    str_fields = {'name', 'setlevel'}
    pk_name = 'name'


class Misc(Model):
    """Store singular data (e.g. date for recurring action)

    Usable through the misc_data, instance of MiscData"""
    pk: T.Union[str, CharField] = CharField(primary_key=True)
    data: T.Any = PickleField()

    str_fields = {'pk'}
    pk_name = 'pk'


models = Model.__subclasses__() + [Library.people.through_model]
if __name__ == '__main__':
    print('Running this as a script will create tables in the DB '
          'and initialize them with basic data. Proceed? (y/n)')
    if not input().lower().startswith('y'):
        sys.exit()
    import hashlib
    if config is not None:
        iterations = config.core.hash_iterations[0]
    else:
        iterations = int(input('iteration count -> '))
    password = hashlib.pbkdf2_hmac('sha256', b'Pa$$w0rd', b'', iterations)
    db.create_tables(models)
    print('created tables...')
    Misc.create(pk='last_script_invocations', data={})
    Member.create(name='SAdmin', password=password, salt=b'', level=4)
    Library.create(name='main')
    print('Finished. Press return to exit')
    input()
