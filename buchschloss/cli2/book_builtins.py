"""builtins"""
import builtins
import datetime

import peewee

from . import objects
from . import common
from .. import models


__all__ = [
    'true', 'false', 'undefined',
    'int', 'float', 'str', 'bool',
    'list', 'frozenlist', 'flist',
    'map', 'frozenmap', 'fmap',
    'date',
    'Book', 'Person', 'Borrow', 'Library', 'Group', 'Member',
    'print', 'iter',
]

true = objects.BookBool(True)
false = objects.BookBool(False)
undefined = objects.BookUndefined(None)
int = objects.BookInt
float = objects.BookFloat
str = objects.BookStr
list = objects.BookList
frozenlist = flist = objects.BookFrozenList
map = objects.BookMap
frozenmap = fmap = objects.BookFrozenMap
bool = objects.BookBool
date = objects.BookDate
Book = objects.ModelWrapper(models.Book)
Person = objects.ModelWrapper(models.Person)
Borrow = objects.ModelWrapper(models.Borrow)
Library = objects.ModelWrapper(models.Library)
Group = objects.ModelWrapper(models.Group)
Member = objects.ModelWrapper(models.Member)


book_equivalent_types = {
    builtins.int: int,
    builtins.list: list,
    builtins.tuple: frozenlist,
    builtins.dict: map,
    builtins.float: float,
    builtins.bool: bool,
    datetime.date: date,
    builtins.str: str,
    models.Person: objects.RecordWrapper,
    models.Book: objects.RecordWrapper,
    models.Library: objects.RecordWrapper,
    models.Group: objects.RecordWrapper,
    models.Borrow: objects.RecordWrapper,
    models.Member: objects.RecordWrapper,
    peewee.ManyToManyQuery: objects.QueryResult,
}

iter = objects.BookFunction(common.ByteCode([
    (common.Opcode.GET_VAR, 0),
    (common.Opcode.GET_ITER,),
    (common.Opcode.RETURN,)],
    (), ['iterable']), ['iterable'])


@objects.PythonFunctionWrapper
def print(value, end=objects.BookStr('\n'), sep=objects.BookStr(' ')):
    builtins.print(value.book_str().value, end=end.value, sep=sep.value)
    return undefined
