"""Used by compiler and interpreter"""
import enum
import math
from argparse import Namespace

from . import objects

VERSION = 0
BYTEORDER = 'little'  # TODO: check which one is used more


class ByteCode:
    def __init__(self, opcodes=None, const=None, names=None):
        self.opcodes = opcodes or []
        self.const = const or []
        self.names = names or []
        self.version = VERSION

    def copy(self):
        return type(self)(self.opcodes, self.const, self.names)

    def __bytes__(self):
        def int_to_bytes(integer: int):
            if 0 <= integer < 100:
                return bytes([integer])
            size = math.ceil((math.log2(abs(integer)+1)+1) / 8)
            if size > 154:  # keep \xff for later extensions
                raise OverflowError
            return bytes([size+100]) + integer.to_bytes(size, BYTEORDER, signed=True)

        r = int_to_bytes(VERSION)
        r += int_to_bytes(len(self.opcodes))
        for opcode, *args in self.opcodes:
            r += bytes([opcode.id])
            for arg in args:
                assert isinstance(arg, int)
                r += int_to_bytes(arg)
        r += int_to_bytes(len(self.const))
        for const in self.const:
            if isinstance(const, objects.BookInt):
                r += int_to_bytes(ConstType.INT.id)
                r += int_to_bytes(const.value)
            elif isinstance(const, objects.BookFloat):
                r += int_to_bytes(ConstType.FLOAT.id)
                raise NotImplementedError("can't dtroe const floats yet")
            elif isinstance(const, objects.BookStr):
                r += int_to_bytes(ConstType.STR.id)
                r += int_to_bytes(len(const.value.encode()))
                r += const.value.encode()
            else:
                raise NotImplementedError("can't save const of type"
                                          + type(const).__name__)
        r += int_to_bytes(len(self.names))  # keep this in for symmetry
        for name in self.names:
            r += int_to_bytes(len(name.encode())) # we shouldn't need the .encode() part, names asr ASCII
            r += name.encode()
        return r


class IDMapEnumMeta(enum.EnumMeta):
    def __new__(mcs, *args, **kwargs):
        new_cls = super().__new__(mcs, *args, **kwargs)
        id_map = {}
        for val in new_cls:
            id_map[val.id] = val
        new_cls.id_map = id_map
        return new_cls

    def __call__(cls, value, names=None, *, module=None, qualname=None, type=None, start=1):
        if names is None:
            return cls.id_map[value]
        else:
            return super().__call__(value, names, module=module,
                                    qualname=qualname, type=type, start=start)


class IDMapEnum(enum.Enum, metaclass=IDMapEnumMeta):
    def __getattr__(self, item):
        if item.startswith('_'):
            raise AttributeError
        return getattr(self.value, item)


nums = iter(range(2**5))
class Opcode(IDMapEnum):
    UNARY_OP = Namespace(id=next(nums), nargs=1)
    BINARY_OP = Namespace(id=next(nums), nargs=1)
    CONTAINS = Namespace(id=next(nums), nargs=0)
    CALL_FUNC = Namespace(id=next(nums), nargs=1)
    JUMP_ON_FALSE = Namespace(id=next(nums), nargs=1)
    JUMP = Namespace(id=next(nums), nargs=1)
    SET_VAR = Namespace(id=next(nums), nargs=1)
    SET_ATTR = Namespace(id=next(nums), nargs=1)
    GET_VAR = Namespace(id=next(nums), nargs=1)
    GET_CONST = Namespace(id=next(nums), nargs=1)
    ENTER_ELEM = Namespace(id=next(nums), nargs=0)
    GET_ELEM = Namespace(id=next(nums), nargs=0)
    GET_ATTR = Namespace(id=next(nums), nargs=1)
    MAKE_LIST = Namespace(id=next(nums), nargs=2)
    MAKE_MAP = Namespace(id=next(nums), nargs=2)
    CLEAR = Namespace(id=next(nums), nargs=0)
    GET_ITER = Namespace(id=next(nums), nargs=0)
    FOR_ITER = Namespace(id=next(nums), nargs=1)
    RETURN = Namespace(id=next(nums), nargs=0)


nums = iter(range(2**4))
class BinaryOp(IDMapEnum):
    ADD = Namespace(id=next(nums), func='add')
    SUB = Namespace(id=next(nums), func='sub')
    MUL = Namespace(id=next(nums), func='mul')
    DIV = Namespace(id=next(nums), func='div')
    LOG_AND = Namespace(id=next(nums), func='land')
    LOG_OR = Namespace(id=next(nums), func='lor')
    GREATER_THAN = Namespace(id=next(nums), func='gt')
    GREATER_EQUAL = Namespace(id=next(nums), func='ge')
    LESS_THAN = Namespace(id=next(nums), func='lt')
    LESS_EQUAL = Namespace(id=next(nums), func='le')
    EQUAL = Namespace(id=next(nums), func='eq')
    NOT_EQUAL = Namespace(id=next(nums), func='ne')


nums = iter(range(2**2))
class UnaryOp(IDMapEnum):
    LOG_NOT = Namespace(id=next(nums), func='lnot')
    PLUS = Namespace(id=next(nums), func='pos')
    MINUS = Namespace(id=next(nums), func='neg')


nums = iter(range(2**2))
class ConstType(IDMapEnum):
    INT = Namespace(id=next(nums))
    FLOAT = Namespace(id=next(nums))
    STR = Namespace(id=next(nums))
    FUNC = Namespace(id=next(nums))
