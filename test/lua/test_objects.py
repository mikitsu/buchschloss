"""test lua/objects.py"""
import functools

import lupa
import pytest

from buchschloss import core
from buchschloss import lua
from buchschloss import utils
from buchschloss.lua import objects


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
        elif item in ('_str', '_items', '_instance'):  # _bool and _call are always set
            raise AttributeError
        else:
            return self._default

    def __getitem__(self, item):
        try:
            return self._items[item]
        except (KeyError, IndexError, AttributeError):
            return self._default

    def __instancecheck__(self, instance):
        return self._instance(instance, self)


def test_action_ns():
    FLAG = object()

    def view_ns(a, *, login_context):
        assert login_context is FLAG
        if a == 1:
            return Dummy(a=FLAG)
        else:
            raise core.BuchSchlossBaseError('', '')

    def new(param, *, other_param, login_context):
        assert login_context is FLAG
        return param, other_param

    # noinspection PyArgumentList
    rt = lupa.LuaRuntime(attribute_handlers=(lua.lua_get, lua.lua_set))
    dummy = Dummy(view_ns=view_ns, new=new, _call=lambda s, dns, runtime=None: dns)
    ns_book = objects.LuaActionNS(dummy, login_context=FLAG, runtime=rt)
    rt.globals()['book'] = ns_book
    with pytest.raises(AttributeError):
        rt.eval('book.view_str')
    assert rt.eval('book.view_ns') is not None
    assert rt.eval('book.new')
    assert rt.eval('book.view_ns(1).a') is FLAG
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


def test_data_ns(monkeypatch):
    """test LuaDataNS"""
    monkeypatch.setattr(core, 'DataNamespace', Dummy)
    data = Dummy(a=1, b=Dummy(x=1), c=[Dummy(x=2), Dummy(x=3)])
    rt = lupa.LuaRuntime(attribute_handlers=(lua.lua_get, lua.lua_set))  # noqa
    rt.globals()['ldn'] = objects.LuaDataNS(data, runtime=rt)
    assert rt.eval('type(ldn)') == 'userdata'
    assert rt.eval('ldn.a') == 1
    assert rt.eval('type(ldn.b)') == 'userdata'
    assert rt.eval('ldn.b.x') == 1
    assert rt.eval('type(ldn.c)') == 'table'
    assert rt.eval('ldn.c[1].x') == 2


def test_login_context():
    """test LuaLoginContext"""
    rt = lupa.LuaRuntime()
    llc = functools.partial(objects.LuaLoginContext, runtime=rt)
    rt.globals()['guest_lc'] = llc(core.guest_lc)
    rt.globals()['internal_lc'] = llc(core.internal_priv_lc)
    rt.globals()['member_lc'] = llc(
        core.LoginType.MEMBER(name='asdf', level=3))
    rt.globals()['script_lc'] = llc(
        core.LoginType.SCRIPT(name='qwert', level=2, invoker=core.guest_lc)
    )
    assert rt.eval('guest_lc.type == "GUEST"')
    assert rt.eval('internal_lc.level == 10')
    assert rt.eval('member_lc.name == "asdf"')
    assert rt.eval('guest_lc.name == nil')
    assert rt.eval('internal_lc.invoker == nil')
    with pytest.raises(AttributeError):
        rt.eval('guest_lc.doesnotexist')
    assert rt.eval('script_lc.level == 2')
    assert rt.eval('script_lc.invoker.type == "GUEST"')
    assert rt.eval('script_lc.invoker.level == 0')
    assert rt.eval('script_lc.invoker.name == nil')


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
