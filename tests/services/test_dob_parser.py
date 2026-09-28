import datetime as dt

from backend.app.services.sanctions.dob_parser import parse_dob


def test_exact_date():
    exact, year = parse_dob("19 Jun 1951")
    assert exact == dt.date(1951, 6, 19)
    assert year == 1951


def test_circa_year_only():
    exact, year = parse_dob("circa 1965")
    assert exact is None
    assert year == 1965


def test_year_range_uses_first_year():
    exact, year = parse_dob("1965 to 1967")
    assert exact is None
    assert year == 1965


def test_none_input():
    assert parse_dob(None) == (None, None)


def test_empty_string():
    assert parse_dob("") == (None, None)


def test_unparseable_text_without_year():
    assert parse_dob("unknown") == (None, None)
