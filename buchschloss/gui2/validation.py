"""validation"""

import functools
import itertools
import typing as T
from ..misc import validation as mval
from .. import misc
from .. import config
from .. import utils


def clean_isbn(user_isbn: str) -> T.Sequence[int]:
    isbn = []
    for digit in user_isbn:
        if digit.isdigit():
            isbn.append(int(digit))
        elif digit in 'Xx':
            isbn.append(10)
    if len(isbn) == 9:
        isbn.insert(0, 0)
    if len(isbn) not in (10, 13):
        raise ValueError
    return isbn


def check_isbn(isbn: T.Sequence[int]) -> int:
    weighted_isbn = functools.partial(zip, itertools.cycle((1, 3)))
    if len(isbn) == 10:
        if (sum((10 - i) * x for i, x in enumerate(isbn)) % 11
                or sum(i * x for i, x in enumerate(isbn, 1)) % 11):
            raise ValueError
        else:
            isbn = [9, 7, 8] + list(isbn[:-1])
            isbn.append(-sum(w * d for w, d in weighted_isbn(isbn)) % 10)
            return int(''.join(map(str, isbn)))
    elif len(isbn) == 13:
        if sum(w * d for w, d in weighted_isbn(isbn)) % 10:
            raise ValueError
        else:
            return int(''.join(map(str, isbn)))


ISBN_validator = mval.Validator(
    (clean_isbn, {ValueError: utils.get_name('error_isbn_length')}),
    (check_isbn, {ValueError: utils.get_name('error_isbn_check')})
)

nonempty = mval.Validator((misc.Instance().__call_bool,
                           utils.get_name('error_empty')))

class_validator = mval.Validator(
    str.upper,
    (config.gui2.class_regex.pattern, utils.get_name('error_invalid_class')),
)

int_list = mval.Validator((lambda L: list(map(int, L)),
                           {ValueError: utils.get_name('must_be_int_list')}))

type_int = mval.Validator((int, {ValueError: utils.get_name('must_be_int')}))

none_on_empty = mval.Validator(lambda s: s or None)

int_or_none = mval.Validator((lambda s: int(s) if s else None,
                              {ValueError: utils.get_name('must_be_int')}))

script_name = mval.Validator(
    nonempty,
    (r'^[a-zA-Z0-9 _-]*$', utils.get_name('invalid_char')),
)
