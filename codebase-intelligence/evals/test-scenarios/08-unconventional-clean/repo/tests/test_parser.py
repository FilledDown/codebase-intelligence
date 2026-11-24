from calc.parser import parse


def test_precedence():
    assert parse("1 + 2 * 3".split()) == 7.0
