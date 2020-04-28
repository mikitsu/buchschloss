"""test cli2/objects.py"""

import lupa
import pytest

from buchschloss import core
from buchschloss import cli2
from buchschloss import utils
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

    def view_ns(a, *, login_context):
        assert login_context is FLAG
        if a == 1:
            return FLAG
        else:
            raise core.BuchSchlossBaseError('', '')

    def new(param, *, other_param, login_context):
        assert login_context is FLAG
        return param, other_param

    # noinspection PyArgumentList
    rt = lupa.LuaRuntime(attribute_handlers=(cli2.lua_get, cli2.lua_set))
    dummy = Dummy(view_ns=view_ns, new=new, _call=lambda s, dns, runtime=None: dns)
    objects.LuaDataNS.specific_class[dummy] = dummy
    ns_book = objects.LuaActionNS(dummy, login_context=FLAG, runtime=rt)
    rt.globals()['book'] = ns_book
    with pytest.raises(AttributeError):
        rt.eval('book.view_str')
    assert rt.eval('book.view_ns') is not None
    assert rt.eval('book.new')
    assert rt.eval('book.view_ns(1)') is FLAG
    with pytest.raises(core.BuchSchlossBaseError):
        rt.eval('book.view_ns(2)')
    assert (rt.eval('book.new{param="val 1", other_param="something else"}')
            == ('val 1', 'something else'))
    assert (rt.eval('book.new{"positional", other_param="keyword"}')
            == ('positional', 'keyword'))
    with pytest.raises(TypeError):
        rt.eval('book.new("positional", "as well")')
    with pytest.raises(TypeError):
        rt.eval('book.new{"positional", "as well"}')


def test_data_ns():
    rt = lupa.LuaRuntime()
    dummy = Dummy(a=1, b=[1, 2, 3], c=Dummy(a='1', d=5), e=7)
    objects.LuaDataNS.add_specific(Dummy, 'ad', {'b': Dummy}, {'c': Dummy})
    ldn = objects.LuaDataNS.specific_class[Dummy](dummy, runtime=rt)
    assert ldn.lua_get('a') == 1
    assert list(ldn.lua_get('b')) == [1, 2, 3]
    assert isinstance(ldn.lua_get('c'), objects.LuaDataNS)
    assert ldn.lua_get('c').lua_get('d') == 5
    assert ldn.lua_get('c').lua_get('a') == '1'
    with pytest.raises(AttributeError):
        ldn.lua_get('e')


def test_ui_interaction(monkeypatch):
    def save_arg(return_val=None):
        """return a function that saves its argument when called"""
        def func(arg):
            func.calls.append(arg)
            return return_val
        func.calls = []
        return func
    display = save_arg()
    get_data = save_arg()
    ask = save_arg()
    alert = save_arg()
    get_name = save_arg('get_name_flag')
    monkeypatch.setattr(utils, 'get_name', get_name)
    rt = lupa.LuaRuntime()
    default_cb = {'display': display, 'get_data': get_data}
    rt.globals()['defaults'] = objects.LuaUIInteraction(
        default_cb, 'prefix::', runtime=rt)
    rt.globals()['no_alert'] = objects.LuaUIInteraction(
        {**default_cb, 'ask': ask}, 'prefix::', runtime=rt)
    rt.globals()['no_ask'] = objects.LuaUIInteraction(
        {**default_cb, 'alert': alert}, 'prefix::', runtime=rt)
    rt.execute('no_alert.ask("msg")')
    assert (len(ask.calls) == 1
            and ask.calls[-1] is 'get_name_flag'
            and get_name.calls[-1] == 'prefix::msg')
    rt.execute('no_ask.alert("msg-2")')
    assert (len(alert.calls) == 1
            and alert.calls[-1] is 'get_name_flag'
            and get_name.calls[-1] == 'prefix::msg-2')
    rt.execute('defaults.display{this="a table", with={"sub", "tables"}}')
    assert (len(display.calls) == 1
            and display.calls[-1] == {'this': 'a table', 'with': ['sub', 'tables']}
            and len(get_name.calls) == 2)


def test_requests_bs4(monkeypatch):
    """test the requests and bs4 Lua interfaces"""
    def get(url):
        return {
            'https://test.invalid/plain.txt':
                Dummy(headers={'Content-Type': 'text/plain'},
                      text='<span>This</span> is <b>plain</b> text'),
            'http://sub.test-2.invalid/doc.html':
                Dummy(headers={'Content-Type': 'text/html'},
                      text='<html><head><title>HTML</title></head>'
                           '<body><p id="content">HTML</p></body></html>'),
            'https://test.invalid/garbled':
                Dummy(headers={}, text='<p>html as well</p>')
        }[url]
    monkeypatch.setattr('requests.get', get)
    rt = lupa.LuaRuntime()
    rt.globals()['requests'] = objects.LuaRequestsInterface(runtime=rt)
    assert (rt.eval('requests.get("https://test.invalid/plain.txt")')
            == '<span>This</span> is <b>plain</b> text')
    rt.execute('r = requests.get("http://sub.test-2.invalid/doc.html")')
    assert isinstance(rt.eval('r'), objects.LuaBS4Interface)
    assert rt.eval('r.text') == 'HTMLHTML'
    assert rt.eval('r.select_one("body").text') == 'HTML'
    assert rt.eval("r.select_one('#content').attrs.id") == 'content'
    assert rt.eval('r.select_one("p").text == r.select("p")[1].text')
    assert (rt.eval('requests.get("https://test.invalid/plain.txt", "html").text')
            == 'This is plain text')
    assert (rt.eval('requests.get("https://test.invalid/garbled")')
            == '<p>html as well</p>')
    assert (rt.eval('requests.get("https://test.invalid/garbled", "html").text')
            == 'html as well')
