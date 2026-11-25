from datetime import date, datetime
from decimal import Decimal

import pytest

from ekstre import fold, parse_amount, parse_date


@pytest.mark.parametrize(
    ("raw", "folded"),
    [
        ("AÇIKLAMA", "aciklama"),
        ("İŞLEM TUTARI", "islem tutari"),
        ("İşlem  Tarihi", "islem tarihi"),
        ("Valör", "valor"),
        ("BORÇ", "borc"),
        (None, ""),
    ],
)
def test_fold(raw, folded):
    assert fold(raw) == folded


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("-22.936,29", "-22936.29"),
        ("1.250,00 TL", "1250.00"),
        ("1.250,00-", "-1250.00"),
        ("(75,50)", "-75.50"),
        ("+300", "300"),
        ("₺ 12,5", "12.5"),
        ("1,234,567.89", "1234567.89"),
        ("1.234.567", "1234567"),
        ("12.500", "12500"),
        ("12.5", "12.5"),
        ("1\xa0250,00", "1250.00"),
        (45000.0, "45000.0"),
        (0.1, "0.1"),
        (7, "7"),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", [None, "", "TL", "Toplam", True, "-"])
def test_parse_amount_none(raw):
    assert parse_amount(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("03.11.2026", date(2026, 11, 3)),
        ("3/11/2026", date(2026, 11, 3)),
        ("03-11-26", date(2026, 11, 3)),
        ("2026-11-03", date(2026, 11, 3)),
        ("03.11.2026 14:32", date(2026, 11, 3)),
        ("03.11.2026 14:32:05", date(2026, 11, 3)),
        (datetime(2026, 11, 3, 9, 0), date(2026, 11, 3)),
        (date(2026, 11, 3), date(2026, 11, 3)),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "Toplam", "31.02.2026", "Borç: 2.312,40", 45000])
def test_parse_date_none(raw):
    assert parse_date(raw) is None
