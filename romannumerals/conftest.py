from pytest import fixture


@fixture
def decimal_to_roman_testcases():
    return {
        1: 'I',  2: 'II',  3: 'III',  4: 'IV',  5: 'V',
        6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X'
    }
