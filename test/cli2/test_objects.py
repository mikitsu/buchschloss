"""test cli2/objects.py"""

import lupa
import pytest

from buchschloss import core
from buchschloss.cli2 import objects


class Dummy:  # TODO: move this out to misc
    """Provide a dummy object

    special attributes:
        _default: a default item to be returned when the requested one is not set
        _str: the string representation of self
        _call: a callable to call (default: return self)
        _bool: value to return when __bool__ is called
        _items: mapping or sequence to delegate __getitem__ to. _default will be returned on Key, Index or AttributeError
    """
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
        if item == '_default':
            return self
        elif item in ('_str', '_items'):  # _bool and _call are always set
            raise AttributeError
        else:
            return self._default

    def __getitem__(self, item):
        try:
            return self._items[item]
        except (KeyError, IndexError, AttributeError):
            return self._default


def test_action_ns():
    FLAG = object()

    def view_ns(a):
        if a == 1:
            return FLAG
        else:
            raise core.BuchSchlossBaseError('', '')

    rt = lupa.LuaRuntime()
    dummy = Dummy(view_ns=view_ns)
    objects.LuaDataNS.specific_class[dummy] = None
    ns_book = objects.LuaActionNS(dummy, runtime=rt)
    rt.globals()['book'] = ns_book
    with pytest.raises(AttributeError):
        rt.eval('book.view_str')
    assert rt.eval('book.view_ns') is not None
    assert rt.eval('book.view_ns(1)').data_ns is FLAG
    assert rt.eval('book.view_ns(2)') is None


def test_data_ns():
    rt = lupa.LuaRuntime()
    dummy = Dummy(a=1, b=[1, 2, 3], c=Dummy(a='1', d=5), e=7)
    objects.LuaDataNS.add_specific(Dummy, 'ad', 'b', {'c': Dummy})
    ldn = objects.LuaDataNS.specific_class[Dummy](dummy, runtime=rt)
    assert ldn.lua_get('a') == 1
    assert list(ldn.lua_get('b')) == [1, 2, 3]
    assert isinstance(ldn.lua_get('c'), objects.LuaDataNS)
    assert ldn.lua_get('c').lua_get('d') == 5
    assert ldn.lua_get('c').lua_get('a') == '1'
    with pytest.raises(AttributeError):
        ldn.lua_get('e')
