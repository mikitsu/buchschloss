"""interpreter"""

import typing

try:
    from . import book_builtins
    from .common import ByteCode, Opcode, BinaryOp, UnaryOp
    from . import objects
except ImportError:
    print('absolute mode')
    # noinspection PyUnresolvedReferences
    from common import ByteCode, Opcode, BinaryOp, UnaryOp
    import book_builtins
    import objects

T = typing


def interpret(bytecode, global_vars, local_vars):
    def exec_unary_op():
        op = UnaryOp(args[0])
        obj = stack.pop()
        func = 'book_' + op.func
        stack.append(getattr(obj, func)())

    def exec_binary_op():
        obj2 = stack.pop()
        obj1 = stack.pop()
        op = BinaryOp(args[0])
        stack.append(binary_op(op, obj1, obj2))

    def exec_contains():
        stack.append(stack.pop().book_contains(stack.pop()))

    def exec_call_func():
        nonlocal stack
        if args[0]:
            func_args = stack[-args[0]:]
        else:
            func_args = ()
        func = stack[~args[0]]
        stack = stack[:~args[0]]
        stack.append(func.book_call(func_args, global_vars))

    def exec_jump_on_false():
        nonlocal i
        if (objects.BookBool.book_construct([stack.pop()], {})
                is not book_builtins.true):
            i = args[0]
            return True

    def exec_jump():
        nonlocal i
        i = args[0]
        return True

    def exec_set_var():
        name = bytecode.names[args[0]]
        var = stack.pop()
        local_vars[name] = var

    def exec_set_attr():
        name = bytecode.names[args[0]]
        val = stack.pop()
        obj = stack.pop()
        obj.book_setattr(name, val)

    def exec_get_var():
        name = bytecode.names[args[0]]
        try:
            var = local_vars[name]
        except KeyError:
            try:
                var = global_vars[name]
            except KeyError:
                for elem in reversed(elem_context):
                    var = elem.book_elem_var(name)
                    if var is not book_builtins.undefined:
                        break
                else:
                    if name in book_builtins.__all__:
                        var = getattr(book_builtins, name)
                    else:
                        var = book_builtins.undefined
        stack.append(var)

    def exec_get_elem():
        elem = stack.pop()
        obj = elem_context.pop()
        stack.append(obj.book_getelem(elem))

    def exec_get_attr():
        name = bytecode.names[args[0]]
        obj = stack.pop()
        stack.append(obj.book_getattr(name))

    def exec_make_list():
        length = args[0]
        value = list(reversed([stack.pop() for _ in range(length)]))
        new_list = (objects.BookFrozenList if args[1] else objects.BookList)(value)
        stack.append(new_list)

    def exec_make_map():
        length = args[0]
        # noinspection PyTypeChecker
        value = dict(reversed([reversed([stack.pop(), stack.pop()])
                               for _ in range(length)]))
        new_map = (objects.BookFrozenMap if args[1] else objects.BookMap)(value)
        stack.append(new_map)

    def exec_clear():
        nonlocal stack
        stack = []

    def exec_for_iter():
        nonlocal i
        val = stack.pop().book_next(global_vars)
        if val is book_builtins.undefined:
            i = args[0]
            return True
        else:
            stack.append(val)

    opcode_map = {
        Opcode.UNARY_OP: exec_unary_op,
        Opcode.BINARY_OP: exec_binary_op,
        Opcode.CONTAINS: exec_contains,
        Opcode.CALL_FUNC: exec_call_func,
        Opcode.JUMP_ON_FALSE: exec_jump_on_false,
        Opcode.JUMP: exec_jump,
        Opcode.SET_VAR: exec_set_var,
        Opcode.SET_ATTR: exec_set_attr,
        Opcode.GET_VAR: exec_get_var,
        Opcode.GET_CONST: lambda: stack.append(bytecode.const[args[0]]),
        Opcode.ENTER_ELEM: lambda: elem_context.append(stack.pop()),
        Opcode.GET_ELEM: exec_get_elem,
        Opcode.GET_ATTR: exec_get_attr,
        Opcode.MAKE_LIST: exec_make_list,
        Opcode.MAKE_MAP: exec_make_map,
        Opcode.CLEAR: exec_clear,
        Opcode.FOR_ITER: exec_for_iter,
        Opcode.GET_ITER: lambda: stack.append(stack.pop().book_iter(global_vars)),
    }
    stack: T.List[objects.BookObject] = []
    elem_context = []
    i = 0
    while i < len(bytecode.opcodes):
        opcode, *args = bytecode.opcodes[i]
        if opcode is Opcode.RETURN:
            return stack.pop()
        elif not opcode_map[opcode]():
            i += 1
    return stack

# operations


def binary_op(optype, obj1, obj2):
    opname = optype.func
    r_obj1 = getattr(obj1, 'book_'+opname)(obj2)
    if r_obj1 is book_builtins.undefined:
        return getattr(obj2, 'book_r'+opname)(obj1)
    else:
        return r_obj1
