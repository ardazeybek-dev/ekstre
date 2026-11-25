"""Guess what a transaction is from its description.

Rules run on the folded (lowercase ASCII) description and the first hit
wins: the purpose (salary, card payment, bill) comes before the transfer
channel (FAST, EFT, havale) that carried it.

Words are matched as stems from the start of a word, so Turkish suffixes
still match: ``fatura`` finds ``FATURASI``, ``maas`` finds ``MAAŞI``.
Short abbreviations must stand alone instead, so ``POS`` does not fire
inside ``POSTA``; an apostrophe suffix (``ATM'DEN``) is still fine.
"""

from __future__ import annotations

import re

from .parse import fold

TYPES = (
    "salary",
    "card_payment",
    "bill",
    "tax",
    "interest",
    "fee",
    "atm",
    "pos",
    "fast",
    "eft",
    "havale",
    "other",
)

# (type, stems that may take a suffix, abbreviations that must stand alone)
_RULES: tuple[tuple[str, str, str], ...] = (
    ("salary", "maas|ucret odeme|personel odeme", ""),
    ("card_payment", "kredi kart|kart borc", "kk"),
    (
        "bill",
        "fatura|otomatik odeme|elektrik|dogalgaz|su idaresi|telekom|turkcell|vodafone|superonline",
        "",
    ),
    ("tax", "vergi|harci", "sgk|gib|mtv|harc|bsmv|kkdf"),
    ("interest", "faiz|getiri", ""),
    ("fee", "komisyon|masraf|ucreti|hesap isletim|kart aidat", ""),
    ("atm", "bankamatik|nakit cek|para cek|para yatir", "atm"),
    ("pos", "alisveris|harcama|sanal pos", "pos"),
    ("fast", "", "fast"),
    ("eft", "", "eft"),
    ("havale", "havale|virman", ""),
)


def _compile(stems: str, abbreviations: str) -> re.Pattern[str]:
    parts = []
    if stems:
        parts.append(rf"\b(?:{stems})")
    if abbreviations:
        parts.append(rf"\b(?:{abbreviations})\b")
    return re.compile("|".join(parts))


_COMPILED = tuple((name, _compile(stems, abbr)) for name, stems, abbr in _RULES)


def classify(description: str) -> str:
    """Return one of :data:`TYPES` for a transaction description.

    >>> classify("FAST GELEN - GÖNDEREN: DENEME KİŞİ")
    'fast'
    >>> classify("POS SATIŞ ÖRNEK MARKET")
    'pos'
    >>> classify("KASIM MAAŞI")
    'salary'
    """
    text = fold(description)
    for name, pattern in _COMPILED:
        if pattern.search(text):
            return name
    return "other"


_IBAN_RE = re.compile(r"\bTR(?:\s?\d){24}\b", re.IGNORECASE)


def iban_is_valid(iban: str) -> bool:
    """Check a Turkish IBAN with the ISO 13616 mod-97 checksum."""
    s = re.sub(r"\s", "", iban).upper()
    if not re.fullmatch(r"TR\d{24}", s):
        return False
    rearranged = s[4:] + s[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def find_iban(text: str) -> str | None:
    """First valid Turkish IBAN in the text, without spaces, or ``None``."""
    for match in _IBAN_RE.finditer(text or ""):
        candidate = re.sub(r"\s", "", match.group(0)).upper()
        if iban_is_valid(candidate):
            return candidate
    return None


# A counterparty is only returned when the bank labelled it. Guessing a name
# out of free text produces confident nonsense, so unlabelled rows give None.
_LABELS = (
    r"g[oö]nderen(?:\s+ad[ıi])?",
    r"al[ıi]c[ıi](?:\s+ad[ıi])?",
    r"kar[sş][ıi]\s+taraf",
    r"kimden",
    r"kime",
)
_LABEL_RE = re.compile(rf"(?:{'|'.join(_LABELS)})\s*[:=]\s*", re.IGNORECASE)
_STOP_RE = re.compile(
    rf"\s*(?:[,;|/]|\bTR\d{{2}}|\bIBAN\b|\bA[CÇ]IKLAMA\b|(?:{'|'.join(_LABELS)})\s*[:=])",
    re.IGNORECASE,
)


def find_counterparty(text: str) -> str | None:
    """Name after a ``GÖNDEREN:`` / ``ALICI:`` style label, or ``None``."""
    match = _LABEL_RE.search(text or "")
    if not match:
        return None
    rest = text[match.end() :]
    stop = _STOP_RE.search(rest)
    # Trailing dots are kept: they end company suffixes such as "A.Ş.".
    name = (rest[: stop.start()] if stop else rest).strip(" -")
    return name or None
