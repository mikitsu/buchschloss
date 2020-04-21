"""Test the lua stdlib"""
import collections
import datetime
import types

from buchschloss import core
from buchschloss import cli2
from buchschloss.cli2 import objects


class DummyActionNS:
    """Save all calls and return fabricated results"""

    def __init__(self, results):
        self.results = {k: iter(v) for k, v in results.items()}
        self.calls = collections.defaultdict(list)

    def __getattr__(self, item):
        def func(*args, **kwargs):
            self.calls[item].append((args, kwargs))
            return next(self.results.get(item, iter(())), None)
        return func


def test_new(monkeypatch):
    """test <Model>:new()"""
    flag = object()
    book_dummy = DummyActionNS({'new': [1, 2, 3]})
    monkeypatch.setattr(core, 'Book', book_dummy)
    monkeypatch.setitem(objects.LuaDataNS.specific_class, book_dummy,
                        type('LuaDummyDataNS', (objects.LuaDataNS,), {
                            'get_allowed': (),
                            'wrap_iter': {},
                            'wrap_data_ns': {}
                        }))
    rt = cli2.prepare_runtime(flag)
    assert rt.eval('Book:new{author="author", title="title"}') == 1
    rt.execute('Book:new({year=0, isbn=123})')
    assert tuple(book_dummy.calls['new']) == (
        ((), {'author': 'author', 'title': 'title', 'login_context': flag}),
        ((), {'year': 0, 'isbn': 123, 'login_context': flag}),
    )


def test_view(monkeypatch):
    """test <Model>[<pk>]"""
    flag = object()
    person_dummy = DummyActionNS({'view_ns': [
        types.SimpleNamespace(first_name='first', pay_date=datetime.datetime(1965, 1, 31)),
        types.SimpleNamespace(first_name='first', pay_date=None),
    ]})
    monkeypatch.setattr(core, 'Person', person_dummy)
    monkeypatch.setitem(objects.LuaDataNS.specific_class, person_dummy,
                        type('LuaDummyDataNS', (objects.LuaDataNS,), {
                            'get_allowed': ('first_name', 'pay_date'),
                            'wrap_iter': {},
                            'wrap_data_ns': {}
                        }))
    rt = cli2.prepare_runtime(flag)
    assert tuple(rt.execute(
        'date = Person[123].pay_date; return {date.day, date.month, date.year}')
                 .values()) == (31, 1, 1965)
    assert rt.eval('Person[124].first_name') == 'first'
    assert tuple(person_dummy.calls['view_ns']) == (
        ((123,), {'login_context': flag}),
        ((124,), {'login_context': flag}),
    )
