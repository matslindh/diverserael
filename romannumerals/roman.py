numerals = (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')


def to_roman_numeral(decimal_value: int):
    output = ''

    for number, char in numerals:
        while decimal_value >= number:
            output += char
            decimal_value -= number

    return output
