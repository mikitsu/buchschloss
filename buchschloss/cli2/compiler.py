"""compiler"""

import typing as T
import lark

try:
    from .common import ByteCode, Opcode, BinaryOp, UnaryOp
    from . import book_builtins
    from . import objects
except ImportError:
    print('absolute mode')
    # noinspection PyUnresolvedReferences
    from common import ByteCode, Opcode, BinaryOp, UnaryOp
    import book_builtins
    import objects

try:
    with open('./cli2/grammar.lark', encoding='UTF-8') as f:
        GRAMMAR = f.read()
except FileNotFoundError:
    with open('./grammar.lark', encoding='UTF-8') as f:
        GRAMMAR = f.read()


class CompilingError(Exception):
    pass


@lark.v_args(inline=True)
class ByteCodeTransform(lark.Transformer):

    def __init__(self, bytecode):
        self.bytecode = bytecode
        self.stored_bytecodes = []  # used for functions
        self.dont_cut_flag = False
        self.frozen_collection = False

    # helper methods

    def add_const(self, value, opcode: T.Optional[Opcode] = Opcode.GET_CONST):
        return self.add_to_data(value, self.bytecode.const, opcode)

    def add_name(self, value, opcode):
        return self.add_to_data(str(value), self.bytecode.names, opcode)

    def add_to_data(self, value, container, opcode):
        if value in container:
            idx = container.index(value)
        else:
            idx = len(container)
            container.append(value)
        if opcode is not None:
            self.bytecode.opcodes.append((opcode, idx))
        return idx

    # handlers

    def start(self, code):
        for i, opcode in enumerate(self.bytecode.opcodes):
            if opcode[0] in (Opcode.JUMP, Opcode.JUMP_ON_FALSE, Opcode.FOR_ITER):
                opcode[1] += i

    for opcode, opfamily, names in [
            (Opcode.BINARY_OP, BinaryOp,
             ('add sub mul div log_and log_or less_than less_equal '
              'greater_than greater_equal equal not_equal').split()),
            (Opcode.UNARY_OP, UnaryOp,
             'log_not minus plus'.split())
            ]:
        # functools.partial can't be used (I assume it isn't a descriptor)
        for name in names:
            opid = getattr(opfamily, name.upper()).value.id

            def op_handler(self, *items, _opid=opid, _opcode=opcode):
                self.bytecode.opcodes.append((_opcode, _opid))

            locals()[name] = op_handler

    def contains(self, *items):
        self.bytecode.opcodes.append((Opcode.CONTAINS,))

    def integer(self, value):
        return self.add_const(objects.BookInt(int(value)))

    def float(self, value):
        return self.add_const(objects.BookFloat(float(value)))

    def string(self, value):
        return self.add_const(objects.BookStr(str(value)[1:-1]))

    def name(self, name):
        return self.add_name(name, Opcode.GET_VAR)

    def set_var_stmt(self, name, val):
        self.add_name(name, Opcode.SET_VAR)
        return None

    def set_attr_stmt(self, obj, name, value):
        self.add_name(name, Opcode.SET_ATTR)

    def func_begin(self):
        self.stored_bytecodes.append(self.bytecode)
        self.bytecode = ByteCode()

    def func_expr(self, arg_list, block):
        arg_names = [self.add_name(a, None) for a in arg_list.children]
        func = objects.BookFunction(self.bytecode, arg_names)
        self.bytecode = self.stored_bytecodes.pop()
        return self.add_const(func)

    def return_stmt(self, value):
        self.bytecode.opcodes.append((Opcode.RETURN,))

    def if_stmt(self, cond_start, cond, block_start, else_start=None):
        opcodes = self.bytecode.opcodes
        opcodes.insert(block_start, [Opcode.JUMP_ON_FALSE,
                                     len(opcodes[block_start:else_start])
                                     + 1 + (else_start is not None)])
        if else_start is not None:
            opcodes.insert(else_start+1, [Opcode.JUMP, len(opcodes[else_start:])])
        return cond_start  # for else if

    def while_stmt(self, cond_start, cond, block_start):
        opcodes = self.bytecode.opcodes
        opcodes.append([Opcode.JUMP, ~len(opcodes[cond_start:])])
        opcodes.insert(block_start, [Opcode.JUMP_ON_FALSE, len(opcodes[block_start:])+1])

    def for_stmt(self, expr_start, name, iterable, block_start):
        opcodes = self.bytecode.opcodes
        opcodes_pre = opcodes[:block_start]
        opcodes_post = opcodes[block_start:]
        iter_var = '.for{}'.format(sum(Opcode.FOR_ITER is opcode[0]
                                       for opcode in opcodes_post))
        iter_var = self.add_name(iter_var, None)
        value_var = self.add_name(name, None)
        opcodes_post.append([Opcode.JUMP, -len(opcodes_post)-3])
        opcodes_middle = [
            (Opcode.GET_ITER,),
            (Opcode.SET_VAR, iter_var),
            (Opcode.GET_VAR, iter_var),
            [Opcode.FOR_ITER, len(opcodes_post)+2],
            (Opcode.SET_VAR, value_var)
        ]
        self.bytecode.opcodes = opcodes_pre+opcodes_middle+opcodes_post

    def dont_cut(self):
        self.dont_cut_flag = True
        return len(self.bytecode.opcodes)

    def block_begin(self):
        self.dont_cut_flag = False
        return len(self.bytecode.opcodes)

    def block(self, begin, content):
        if begin != len(self.bytecode.opcodes):  # empty
            self.limit(None)
        return begin

    def limit(self, val):
        opcodes = self.bytecode.opcodes
        if (not opcodes) or getattr(self, 'dont_cut_flag', False):
            return
        if opcodes[-1][0] in (Opcode.GET_VAR, Opcode.GET_CONST):
            opcodes.pop()  # lookup has no side effects
        elif opcodes[-1][0] not in (Opcode.JUMP_ON_FALSE, Opcode.SET_VAR,
                                    Opcode.JUMP, Opcode.CLEAR):
            opcodes.append((Opcode.CLEAR,)) 

    def call(self, name, *args):
        self.bytecode.opcodes.append((Opcode.CALL_FUNC, len(args)))

    def elem_enter(self):
        self.bytecode.opcodes.append((Opcode.ENTER_ELEM,))

    def elem_lookup(self, start, obj, elem):
        self.bytecode.opcodes.append((Opcode.GET_ELEM,))

    def attr_lookup(self, var, name):
        idx = self.add_name(name, None)
        self.bytecode.opcodes.append((Opcode.GET_ATTR, idx))

    def list(self, *elements):
        if self.frozen_collection:
            length = len(elements)-1
        else:
            length = len(elements)
        self.bytecode.opcodes.append((Opcode.MAKE_LIST, length, self.frozen_collection))
        self.frozen_collection = False

    def map(self, *elements):
        self.bytecode.opcodes.append((Opcode.MAKE_MAP, len(elements)//2,
                                      self.frozen_collection))
        self.frozen_collection = False

    def frozen(self):
        self.frozen_collection = True


bytecode_template = ByteCode()
parser = lark.Lark(GRAMMAR, parser='lalr', transformer=ByteCodeTransform(bytecode_template))


def book_compile(code):
    bytecode_template.__init__()
    try:
        parser.parse(code)
    except (lark.exceptions.ParseError, lark.exceptions.LexError) as e:
        raise CompilingError(str(e)) from None
    return bytecode_template.copy()


def print_bc(code):
    dis(book_compile(code))


def dis(bc):
    for i, code in enumerate(bc.opcodes):
        code, *args = code
        print(i, code.name, *args, end='')
        if code is Opcode.GET_CONST:
            print(f' ({bc.const[args[0]]!r})')
        elif code in (Opcode.GET_VAR, Opcode.SET_VAR, Opcode.GET_ATTR,
                      Opcode.SET_ATTR):
            print(f' ({bc.names[args[0]]})')
        elif code is Opcode.BINARY_OP:
            print(f' ({BinaryOp(args[0]).name})')
        elif code is Opcode.UNARY_OP:
            print(f' ({UnaryOp(args[0]).name})')
        else:
            print()
