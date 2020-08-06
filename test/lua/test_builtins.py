"""Test the lua stdlib"""
import collections
import datetime
import types

from buchschloss import core
from buchschloss import lua


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
    book_dummy = DummyActionNS({'new': [1, 2, 3]})
    monkeypatch.setattr(core, 'Book', book_dummy)
    rt = lua.prepare_runtime(core.guest_lc)
    assert rt.eval('Book:new{author="author", title="title"}') == 1
    rt.execute('Book:new({year=0, isbn=123})')
    assert tuple(book_dummy.calls['new']) == (
        ((), {'author': 'author', 'title': 'title', 'login_context': core.guest_lc}),
        ((), {'year': 0, 'isbn': 123, 'login_context': core.guest_lc}),
    )


def test_view(monkeypatch):
    """test <Model>[<pk>]"""
    person_dummy = DummyActionNS({'view_ns': [
        types.SimpleNamespace(first_name='first', pay_date=datetime.datetime(1965, 1, 31)),
        types.SimpleNamespace(first_name='first', pay_date=None),
    ]})
    monkeypatch.setattr(core, 'Person', person_dummy)
    rt = lua.prepare_runtime(core.guest_lc)
    assert tuple(rt.execute(
        'date = Person[123].pay_date; return {date.day, date.month, date.year}')
                 .values()) == (31, 1, 1965)
    assert rt.eval('Person[124].first_name') == 'first'
    assert tuple(person_dummy.calls['view_ns']) == (
        ((123,), {'login_context': core.guest_lc}),
        ((124,), {'login_context': core.guest_lc}),
    )


def test_specials(monkeypatch):
    """test Borrow:restitute and Group[<id>]:activate"""
    borrow_dummy = DummyActionNS({'restitute': ['A4']})
    group_dummy = DummyActionNS({'activate': [None], 'view_ns': [object()]})
    monkeypatch.setattr(core, 'Borrow', borrow_dummy)
    monkeypatch.setattr(core, 'Group', group_dummy)
    rt = lua.prepare_runtime(core.guest_lc)
    assert rt.eval('Borrow:restitute{123, 456}') == 'A4'
    assert borrow_dummy.calls['restitute'][0] == ((123, 456), {'login_context': core.guest_lc})
    assert rt.eval('Group.g_name:activate{{"1", "2", "3"}, "dest"}') is None
    assert (group_dummy.calls['activate'][0]
            == (('g_name', ['1', '2', '3'], 'dest'), {'login_context': core.guest_lc}))
