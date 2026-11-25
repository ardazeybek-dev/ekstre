"""Low-level parsing of Turkish text, amounts and dates found in bank exports."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_ASCII_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def fold(text: object) -> str:
    """Lowercase Turkish text correctly and strip it to plain ASCII letters.

    Python's ``str.lower`` is not Turkish-aware: ``"AÇIKLAMA".lower()`` gives
    ``"açiklama"`` and ``"İ".lower()`` adds a combining dot. Headers and
    descriptions are compared after this fold, so ``"İŞLEM TUTARI"``,
    ``"İşlem Tutarı"`` and ``"islem tutari"`` all become ``"islem tutari"``.
    """
    if text is None:
        return ""
    s = str(text).replace("İ", "i").replace("I", "ı").lower()
    s = unicodedata.normalize("NFC", s).replace("̇", "")
    s = s.translate(_ASCII_FOLD)
    return " ".join(s.split())


def clean(value: object) -> str:
    """Cell value as a stripped string, with non-breaking spaces removed."""
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


_NOT_NUMBER = re.compile(r"[^\d,.]")


def parse_amount(value: object) -> Decimal | None:
    """Turn a Turkish-formatted amount into a ``Decimal``.

    >>> parse_amount("-22.936,29")
    Decimal('-22936.29')
    >>> parse_amount("1.250,00 TL")
    Decimal('1250.00')
    >>> parse_amount("(75,50)")
    Decimal('-75.50')
    >>> parse_amount("1.250,00-")
    Decimal('-1250.00')

    Numbers that are already numeric (Excel cells) are used as they are.
    Returns ``None`` when the value holds no number.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # repr gives the shortest form that round-trips, so 0.1 stays 0.1.
        return Decimal(repr(value))

    s = clean(value)
    if not s:
        return None
    negative = s.startswith("-") or s.endswith("-") or (s.startswith("(") and s.endswith(")"))
    s = _NOT_NUMBER.sub("", s)
    if not s or not any(ch.isdigit() for ch in s):
        return None

    if "," in s and "." in s:
        # Whichever separator comes last is the decimal one.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if s.count(",") > 1 else s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif "." in s and len(s.rsplit(".", 1)[1]) == 3:
        # "1.250" is ambiguous. Turkish exports write decimals with a comma,
        # so a dot followed by exactly three digits is read as thousands.
        s = s.replace(".", "")

    try:
        number = Decimal(s)
    except InvalidOperation:
        return None
    return -number if negative else number


_DATE_RE = re.compile(
    r"^(?:(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})|(\d{4})-(\d{1,2})-(\d{1,2}))"
    r"(?:[ T]+\d{1,2}[:.]\d{2}(?:[:.]\d{2})?)?$"
)


def parse_date(value: object) -> date | None:
    """Turn a cell into a ``date``.

    Accepts ``date``/``datetime`` objects, ``dd.mm.yyyy`` (also with ``/`` or
    ``-`` and an optional time), ``yyyy-mm-dd`` and two-digit years.
    Returns ``None`` for anything else, which is how non-transaction rows
    (totals, footers, blank lines) are recognised.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = clean(value)
    m = _DATE_RE.match(s)
    if not m:
        return None
    if m.group(1):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
    else:
        year, month, day = int(m.group(4)), int(m.group(5)), int(m.group(6))
    try:
        return date(year, month, day)
    except ValueError:
        return None
