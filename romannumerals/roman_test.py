from roman import to_roman_numeral


def test_decimal_to_roman_numeral(decimal_to_roman_testcases):
    for decimal, roman in decimal_to_roman_testcases.items():
        assert to_roman_numeral(decimal) == roman