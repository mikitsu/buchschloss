"""test utils"""

from buchschloss import config, utils


def test_get_name():
    """Test get_name"""
    config.utils.names = {
        'a': {
            'b': {
                'c': {
                    '*this*': 'ABC',
                    'd': 'ABCD',
                    'e': 'ABCE',
                },
                'e': 'ABE',
            },
            'c': {
                'd': 'ACD',
                'h': 'ACH',
            },
            'f': 'AF',
        },
        'c': {
            'd': 'CD',
            'h': 'CH',
            'i': 'CI',
        },
        'f': 'F',
        'g': 'G',
    }
    assert utils.get_name('a::b::c::d') == 'ABCD'
    assert utils.get_name('a::b::c') == 'ABC'
    assert utils.get_name('a::b::c::e') == 'ABCE'
    assert utils.get_name('a::b::c::h') == 'ACH'
    assert utils.get_name('a::b::c::f') == 'AF'
    assert utils.get_name('a::b::c::i') == 'CI'
    assert utils.get_name('a::b::c::g') == 'G'
    assert utils.get_name('does::not::exist::at::all::c::d') == 'CD'
