"""test compiler"""

from buchschloss.cli2 import compiler, common, book_builtins


def util_print_opcodes(bc):
    for code in bc.opcodes:
        print(f'(common.Opcode.{code[0].name}, %s),'
              % (', '.join(map(str, code[1:]))))


def canon_opcodes(bc):
    return tuple(map(tuple, bc.opcodes))


def test_add():
    bc = compiler.book_compile('x = a+b')
    assert tuple(bc.opcodes) == ((common.Opcode.GET_VAR, 0),
                                 (common.Opcode.GET_VAR, 1),
                                 (common.Opcode.BINARY_OP, 0),
                                 (common.Opcode.SET_VAR, 2))
    assert tuple(bc.names) == ('a', 'b', 'x')
    assert not bc.const


def test_for():
    bc = compiler.book_compile('for x in lst{print(x)}')
    assert canon_opcodes(bc) == (
        (common.Opcode.GET_CONST, 0),
        (common.Opcode.GET_VAR, 0),
        (common.Opcode.CALL_FUNC, 1),
        (common.Opcode.SET_VAR, 3),
        (common.Opcode.GET_VAR, 3),
        (common.Opcode.FOR_ITER, 12),
        (common.Opcode.SET_VAR, 2),
        (common.Opcode.GET_VAR, 1),
        (common.Opcode.GET_VAR, 2),
        (common.Opcode.CALL_FUNC, 1),
        (common.Opcode.CLEAR,),
        (common.Opcode.JUMP, 4)
    )
    assert tuple(bc.names) == ('lst', 'print', 'x', '.for0')
    assert len(bc.const) == 1
    assert bc.const[0] is book_builtins.iter  # not totally sure if is is right...


def test_else_if():
    bc1 = compiler.book_compile('if x{a()}else if y{b()} else {c()}')
    bc2 = compiler.book_compile('if x{a()}else if y{b()} else {c()}')
    assert canon_opcodes(bc1) == canon_opcodes(bc2) == (
        (common.Opcode.GET_VAR, 0),
        (common.Opcode.JUMP_ON_FALSE, 6),
        (common.Opcode.GET_VAR, 1),
        (common.Opcode.CALL_FUNC, 0),
        (common.Opcode.CLEAR,),
        (common.Opcode.JUMP, 15),
        (common.Opcode.GET_VAR, 2),
        (common.Opcode.JUMP_ON_FALSE, 12),
        (common.Opcode.GET_VAR, 3),
        (common.Opcode.CALL_FUNC, 0),
        (common.Opcode.CLEAR,),
        (common.Opcode.JUMP, 15),
        (common.Opcode.GET_VAR, 4),
        (common.Opcode.CALL_FUNC, 0),
        (common.Opcode.CLEAR,),
    )
    assert tuple(bc1.names) == tuple(bc2.names) == tuple('xaybc')
    assert not (bc1.const or bc2.const)
