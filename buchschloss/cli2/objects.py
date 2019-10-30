"""objects"""
from functools import wraps
import datetime
import typing
import peewee
try:
    from. import book_builtins
    from . import interpreter
    from .. import core
except ImportError:
    import book_builtins
    import interpreter
    core = None

T = typing


class BookObjectMeta(type):
    def __getattribute__(cls, name):
        if name.startswith('book_') and name not in (
                'book_class', 'book_construct', 'book_init'):
            return getattr(super().__getattribute__('book_class'), name)
        return super().__getattribute__(name)


class BookObject(metaclass=BookObjectMeta):
    def __init__(self):
        self.book_class = type(self)
        self.book_attrs = {}

    def __init_subclass__(cls):
        if 'book_class' not in vars(cls):
            cls.book_class = BookClass(cls)

    # operations
    book_pos = book_neg = book_add = book_radd = book_sub = book_rsub = \
        book_mul = book_rmul = book_div = book_rdiv = book_gt = book_lt = \
        book_contains = lambda *a, **kw: book_builtins.undefined

    def book_lnot(self):
        b = BookBool.book_construct([self], {})
        if b is book_builtins.true:
            return book_builtins.false
        elif b is book_builtins.false:
            return book_builtins.true
        else:
            return b

    def book_land(self, other):
        b = BookBool.book_construct([self], {})
        if b is book_builtins.true:
            return other
        else:
            return self

    def book_rland(self, other):
        return type(self).book_land(other, self)

    def book_lor(self, other):
        b = BookBool.book_construct([self], {})
        if b is book_builtins.true:
            return self
        else:
            return other

    def book_rlor(self, other):
        return type(self).book_lor(other, self)

    def book_rgt(self, other):
        return self.book_lt(other)

    def book_ge(self, other):
        return interpreter.binary_op(
            interpreter.BinaryOp.LOG_OR,
            interpreter.binary_op(interpreter.BinaryOp.GREATER_THAN, self, other),
            interpreter.binary_op(interpreter.BinaryOp.EQUAL, self, other))

    def book_rge(self, other):
        return self.book_le(other)

    def book_rlt(self, other):
        return self.book_gt(other)

    def book_le(self, other):
        return interpreter.binary_op(
            interpreter.BinaryOp.LOG_OR,
            interpreter.binary_op(interpreter.BinaryOp.LESS_THAN, self, other),
            interpreter.binary_op(interpreter.BinaryOp.EQUAL, self, other))

    def book_rle(self, other):
        return self.book_ge(other)

    def book_eq(self, other):
        return BookBool(self is other)

    def book_ne(self, other):
        return interpreter.binary_op(interpreter.BinaryOp.EQUAL, self, other).book_lnot()

    book_req = book_eq
    book_rne = book_ne

    # transformations

    @staticmethod
    def book_bool():
        return book_builtins.undefined

    @staticmethod
    def book_str():
        return BookStr('<object>')

    # instantiation

    @classmethod
    def book_construct(cls, args, global_vars):
        inst = cls()
        inst.book_init(args, global_vars)
        return inst

    def book_init(self, args, global_vars):
        pass

    # misc

    def book_getattr(self, name):
        return self.book_attrs.get(name, book_builtins.undefined)

    def book_setattr(self, name, value):
        self.book_attrs[name] = value

    @staticmethod
    def book_getelem(value):
        return book_builtins.undefined

    def book_call(self, args, global_vars):
        return book_builtins.undefined

    @staticmethod
    def book_elem_var(name):
        return book_builtins.undefined

    @staticmethod
    def book_next(global_vars):
        return book_builtins.undefined

    @staticmethod
    def book_iter(global_vars):
        return book_builtins.undefined


class BookClass(BookObject):
    book_class = None

    def __init__(self, class_):
        super().__init__()
        self.class_ = class_

    def book_call(self, args, global_vars):
        return self.class_.book_construct(args, global_vars)

    @staticmethod
    def book_str(**kwargs):
        return BookStr('<class>')


def repr_for_wrapper(name):
    def __repr__(self):
        if not hasattr(self, name):
            return '<under construction>'
        else:
            return '{}({!r})'.format(type(self).__qualname__, getattr(self, name))
    return __repr__


class PythonObjectWrapper(BookObject):
    """Represent an exposed Python object

        `value` in class scope is the Python type
        `value` in instance scope is the wrapped Python value
        __eq__ is implemented by comparing .value
        a basic book_construct is provided. For a wider range, see PythonConstruct
    """
    def __init__(self, *value):
        super().__init__()
        self.value = self.value(*value)

    __repr__ = repr_for_wrapper('value')

    def __eq__(self, other):
        if isinstance(other, __class__):
            return self.value == other.value
        else:
            return False

    @classmethod
    def book_construct(cls, args, global_vars):
        if len(args) == 1 and isinstance(args[0], cls):
            return cls(args[0].value)
        else:
            return book_builtins.undefined


class ImmutablePythonObjectWrapper(PythonObjectWrapper):
    def __hash__(self):
        return hash(self.value)


class PythonFunctionWrapper(BookObject):
    def __init__(self, function):
        super().__init__()
        self.function = function

    __repr__ = repr_for_wrapper('function')

    def book_call(self, args, global_vars):
        try:
            return self.function(*args)
        except Exception:
            return book_builtins.undefined

    def book_str(self):
        return BookStr('<Python function "{}">'.format(self.function.__name__))


class OnlyForType:
    types = {}

    def __init__(self, type_id):
        self.type_id = type_id

    def __call__(self, f):
        @wraps(f)
        def wrapper(w_self, other):
            # noinspection PyUnresolvedReferences
            if isinstance(other, __class__.types[self.type_id]):
                return f(w_self, other)
            else:
                return book_builtins.undefined

        return wrapper


def allow_methods(*names, return_type=None):
    """Allow access to the given Python methods of self.model

        If ``return_type`` is None:
            If a method returns a BookObject, return it;
            otherwise, book_builtins.undefined
        otherwise:
            return return_type(<retuned model>)
        ``return_type`` may also be a string of the type It will be resolved
            via globals() on first use
        """
    class WithAllowedMethods(PythonObjectWrapper):
        def book_getattr(self, name):
            nonlocal return_type
            if isinstance(return_type, str):
                return_type = globals()[return_type]
            a = super().book_getattr(name)
            if a is book_builtins.undefined and (
                    name in names
                     ):
                py_method = getattr(self.value, name)

                @PythonFunctionWrapper
                def book_method(*args, **kwargs):
                    try:
                        r = py_method(*args, **kwargs)
                        if return_type is None:
                            if isinstance(r, BookObject):
                                return r
                        else:
                            return return_type(r)
                    except Exception:
                        pass
                    return book_builtins.undefined
                self.book_attrs[name] = book_method
                return book_method
            else:
                return a
    return WithAllowedMethods


def match_signature(*signatures):
    """Wrap a book_call. return undefined for calls with arguments not
        matching one of the given signatures

        A signature is given as sequence of types. If a string is given,
        it is interpreted as a global variable. The sequence should be mutable
        (e.g. a list) in this case.
    """
    signatures = list(signatures)
    resolved_signatures = []

    def wrapper_maker(func):
        @wraps(func)
        def match_signature_wrapper(self, args, global_vars):
            for to_res, sigs in enumerate((resolved_signatures, signatures)):
                for sig in sigs:
                    if len(args) == len(sig):
                        for i, (arg, expected_type) in enumerate(zip(args, sig)):
                            if isinstance(expected_type, str):
                                sig[i] = expected_type = globals()[expected_type]
                            if not isinstance(arg, expected_type):
                                break
                        else:
                            if to_res:
                                resolved_signatures.append(tuple(sig))
                                signatures.remove(sig)
                            return func(self, args, global_vars)
            return book_builtins.undefined
        return match_signature_wrapper
    return wrapper_maker


class PythonConstruct(PythonObjectWrapper):
    value: type

    @classmethod
    def book_construct(cls, args, global_vars):
        try:
            return cls(*(o.value for o in args))
        except Exception:
            return book_builtins.undefined


def python_add(type_id):
    class PythonAdd(PythonObjectWrapper):
        @OnlyForType(type_id)
        def book_add(self, other):
            return type(self)(self.value + other.value)
    return PythonAdd


class PythonBool(PythonObjectWrapper):
    def book_bool(self):
        return BookBool(bool(self.value))


class PythonStr(PythonObjectWrapper):
    def book_str(self):
        return BookStr(str(self.value))


class PythonIn(PythonObjectWrapper):
    def book_contains(self, other):
        return BookBool(other in self.value)


class PythonIter(PythonObjectWrapper):
    def book_iter(self, global_vars):
        return BookIterator(self.value)


def python_elem(exception):
    """Provide a Python __getitem__ for book_getelem calls

        Try to return ``self.value[given_elem.value]`` for other
        PythonObjectWrapper objects. If ``exception`` (may also be a tuple)
        is raised, return book_builtins.undefined
    """
    class PythonElem(PythonObjectWrapper):
        @match_signature((PythonObjectWrapper,))
        def book_getelem(self, value):
            try:
                return self.value[value.value]
            except exception:
                return book_builtins.undefined
    return PythonElem


def python_eq(type_id):
    class PythonEq(PythonObjectWrapper):
        @OnlyForType(type_id)
        def book_eq(self, other):
            return BookBool(self.value == other.value)
    return PythonEq


class BookNumber(python_eq('python-obj'), PythonBool,
                 PythonStr, PythonConstruct, ImmutablePythonObjectWrapper):
    value: T.Union[int, float]

    def book_pos(self):
        return self

    def book_neg(self):
        return type(self)(-self.value)

    @OnlyForType('number')
    def book_add(self, other):
        r = self.value + other.value
        return {int: BookInt, float: BookFloat}[type(r)](r)

    @OnlyForType('number')
    def book_sub(self, other):
        r = self.value - other.value
        return {int: BookInt, float: BookFloat}[type(r)](r)
    
    @OnlyForType('number')
    def book_mul(self, other):
        r = self.value * other.value
        return {int: BookInt, float: BookFloat}[type(r)](r)

    @OnlyForType('number')
    def book_div(self, other):
        r = self.value / other.value
        if r == self.value // other.value:
            return BookInt(r)
        else:
            return {int: BookInt, float: BookFloat}[type(r)](r)

    @OnlyForType('number')
    def book_gt(self, other):
        return BookBool(self.value > other.value)

    @OnlyForType('number')
    def book_lt(self, other):
        return BookBool(self.value < other.value)


class BookInt(BookNumber):
    value: int = int


class BookFloat(BookNumber):
    value: float = float


class BookStr(PythonBool, python_add('str'), python_eq('python-obj'),
              ImmutablePythonObjectWrapper):
    value: str = str

    @OnlyForType('number')
    def book_mul(self, other):
        return type(self)(self.value * other.value)

    @OnlyForType('number')
    def book_rmul(self, other):
        return type(self)(other.value * self.value)

    def book_str(self):
        return self

    @classmethod
    def book_construct(cls, args, global_vars):
        if len(args) == 1:
            return args[0].book_str()
        else:
            return book_builtins.undefined


class SingletonMeta(BookObjectMeta):
    instances = {}

    def __call__(cls, value, *args, **kwargs):
        try:
            return __class__.instances[value]
        except KeyError:
            inst = object.__new__(cls)
            inst.__init__(value, *args, **kwargs)
            __class__.instances[value] = inst
            return inst

    def __repr__(self):
        return '{0.__class__.__name__}({0.value})'.format(self)


class BookBool(python_eq('python-obj'), ImmutablePythonObjectWrapper,
               metaclass=SingletonMeta):
    value: bool = bool

    def book_bool(self):
        return self

    def book_str(self):
        if self.value:
            return BookStr('true')
        else:
            return BookStr('false')

    @classmethod
    def book_construct(cls, args, global_vars):
        if len(args) == 1:
            return args[0].book_bool()
        else:
            return book_builtins.undefined


class BookUndefined(BookObject, metaclass=SingletonMeta):
    def __init__(self, value):
        super().__init__()

    @staticmethod
    def book_str(**kwargs):
        return BookStr('undefined')

    def __hash__(self):
        return hash(None)


class BookListBase(allow_methods('count', 'index', return_type=BookInt),
                   python_add('list'), python_eq('python-obj'),
                   python_elem(IndexError),
                   PythonBool, PythonIn, PythonIter):
    value: list = list

    @classmethod
    @match_signature((BookObject,))
    def book_construct(cls, args, global_vars):
        iterator = args[0].book_iter(global_vars)
        value = []
        v = iterator.book_next(global_vars)
        while v is not book_builtins.undefined:
            value.append(v)
            v = iterator.book_next(global_vars)
        return cls(value)

    def book_str(self):
        return '[{}]'.format(', '.join(o.book_str().value for o in self.value))


class BookList(BookListBase,
               allow_methods('append', 'clear', 'extend', 'insert',
                             'pop', 'remove', 'reverse', 'sort'),
               allow_methods('copy', return_type='BookList'),
               ):

    def __init__(self, value):
        super().__init__(value)
        self.book_attrs['frozen'] = self.frozen

    def book_str(self):
        return BookStr(super().book_str() + 'L')

    @PythonFunctionWrapper
    def set_item(self, name, value):
        pass

    @PythonFunctionWrapper
    def frozen(self):
        return BookFrozenList(self.value)


class BookFrozenList(BookListBase,
                     allow_methods('count', 'index', return_type=BookInt),
                     ):

    def __init__(self, value: T.Iterable):
        super().__init__(value)
        self.book_attrs.update({
            'reversed': PythonFunctionWrapper(self.reversed),
            'sorted': PythonFunctionWrapper(self.sorted),
        })

    def __hash__(self):
        return hash((__class__, tuple(self.value)))

    def book_str(self):
        return BookStr(super().book_str() + 'FL')

    def reversed(self):
        return type(self)(reversed(self.value))

    def sorted(self):
        return type(self)(sorted(self.value))


class BookMapBase(allow_methods('keys', 'values', return_type=BookFrozenList),
                  allow_methods('get'),
                  PythonBool, python_eq('python-obj')):
    value: dict = dict

    def __init__(self, value):
        super().__init__(value)
        self.book_attrs.update({
            'get': PythonFunctionWrapper(self.get),
            'items': PythonFunctionWrapper(self.items),
        })

    @OnlyForType('map')
    def book_add(self, other):
        tmp = self.value.copy()
        tmp.update(other.value)
        return type(self)(tmp)

    def book_str(self):
        return '[{}]'.format(', '.join(
            ': '.join((k.book_str().value, v.book_str().value))
            for k, v in self.value.items()))

    def items(self):
        return BookFrozenList(BookFrozenList(i) for i in self.value.items())

    def get(self, key, default=BookUndefined(None)):
        return self.value.get(key, default)


class BookMap(BookMapBase,
              allow_methods('clear', 'pop', 'setdefault'),
              allow_methods('copy', return_type='BookMap'),
              allow_methods('popitem', return_type='BookFrozenList'),
              ):
    def book_str(self):
        return BookStr(super().book_str() + 'M')

    def book_call(self, args, global_vars):
        if len(args) == 1:
            try:
                return self.value[args[0]]
            except KeyError:
                pass
        elif len(args) == 2:
            self.value[args[0]] = args[1]
        return book_builtins.undefined


class BookFrozenMap(BookMapBase):
    def book_str(self):
        return BookStr(super().book_str() + 'FM')

    def book_call(self, args, global_vars):
        if len(args) == 1:
            try:
                return self.value[args[0]]
            except KeyError:
                pass
        return book_builtins.undefined


class BookFunction(BookObject):
    def __init__(self, bytecode, args):
        super().__init__()
        self.bytecode = bytecode
        self.args = args

    def book_call(self, args, global_vars):
        local_vars = {}
        if len(args) != len(self.args):
            return book_builtins.undefined
        for name, value in zip(self.args, args):
            local_vars[self.bytecode.names[name]] = value
        r = interpreter.interpret(self.bytecode, global_vars, local_vars)
        if isinstance(r, BookObject):
            return r
        else:
            return book_builtins.undefined

    @staticmethod
    def book_str():
        return '<function>'


class BookDate(allow_methods('strftime', BookStr), PythonConstruct,
               PythonStr, ImmutablePythonObjectWrapper):
    value: datetime.date = datetime.date


class BookIterator(PythonObjectWrapper):
    value: T.Iterator = iter

    def book_next(self, global_vars):
        try:
            return next(self.value)
        except StopIteration:
            return book_builtins.undefined

    def book_iter(self, global_vars):
        return self


class SearchQuery(BookObject):
    def __init__(self, query=()):
        super().__init__()
        self.query = query

    __repr__ = repr_for_wrapper('query')

    @OnlyForType('search-query')
    def book_lor(self, other):
        return type(self)((self.query, 'or', other.query))

    @OnlyForType('search-query')
    def book_land(self, other):
        return type(self)((self.query, 'and', other.query))

    def book_str(self):
        return BookStr(repr(self.query))


class SearchName(BookObject):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def __getattribute__(self, item):
        if item.startswith('book_'):
            opname = item[5:]
            if opname in ('eq', 'ne', 'gt', 'ge', 'lt', 'le', 'contains'):
                def maker(other):
                    if isinstance(other, (BookNumber, BookStr, BookBool)):
                        return SearchQuery((self.name, opname, other.value))
                    return book_builtins.undefined
                return maker
        return super().__getattribute__(item)

    def book_getattr(self, name):
        return type(self)('.'.join((self.name, name)))

    def book_setattr(self, name, value):
        return


class ModelWrapper(BookObject):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def book_elem_var(self, name):
        name = name.rstrip('_')
        if isinstance(getattr(self.model, name, None), peewee.Field):
            return SearchName(name)
        else:
            return book_builtins.undefined

    def book_getelem(self, value):
        if isinstance(value, SearchQuery):
            return QueryResult(core.search(self.model, value.query))
        elif (isinstance(value, PythonObjectWrapper)
              and isinstance(value.value, self.model.pk_type)):
            try:
                # TODO: make core object-oriented (i.e. Book.new, Book.search)
                # for this to look much nicer
                return RecordWrapper(getattr(core, 'view_'+self.model.__name__.lower())(value.value))
            except self.model.DoesNotExist:
                return book_builtins.undefined
        else:
            return book_builtins.undefined


class RecordWrapper(PythonStr):
    @staticmethod
    def value(val):
        return val

    def book_getattr(self, name):
        try:
            val = getattr(self.value, name, None)
            return book_builtins.book_equivalent_types[type(val)](val)
        except KeyError:
            return book_builtins.undefined


class QueryResult(BookObject):
    def __init__(self, result):
        super().__init__()
        self.result = result

    def __repr__(self):
        return '{}({})'.format(type(self).__name__, self.result)

    @match_signature((BookInt,))
    def book_call(self, args, global_vars):
        if not isinstance(self.result, tuple):
            self.result = tuple(set(self.result))
        try:
            return RecordWrapper(self.result[args[0].value])
        except IndexError:
            pass
        return book_builtins.undefined

    @staticmethod
    def book_str():
        return BookStr('<query>')


OnlyForType.types = {
    'python-obj': PythonObjectWrapper,
    'number': BookNumber,
    'list': BookListBase,
    'map': BookMapBase,
    'str': BookStr,
    'search-query': SearchQuery,
}
BookObject.book_class = BookClass.book_class = BookClass
