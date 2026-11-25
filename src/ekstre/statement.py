"""Find the transaction table in an export and turn it into transactions."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

from .classify import classify, find_counterparty, find_iban
from .errors import StatementError
from .files import Row, Sheet, read_sheets
from .parse import clean, fold, parse_amount, parse_date


@dataclass(frozen=True)
class Transaction:
    """One line of the statement. ``amount`` is negative for money going out."""

    date: date
    description: str
    amount: Decimal
    balance: Decimal | None = None
    value_date: date | None = None
    reference: str = ""
    type: str = "other"
    counterparty: str | None = None
    iban: str | None = None
    row: int = 0
    """1-based row number in the source sheet, for tracing a line back."""

    @property
    def direction(self) -> str:
        return "in" if self.amount >= 0 else "out"

    def to_dict(self) -> dict[str, str | int | None]:
        """Plain values only: dates as ISO strings, money as exact strings."""
        return {
            "date": self.date.isoformat(),
            "value_date": self.value_date.isoformat() if self.value_date else None,
            "description": self.description,
            "amount": str(self.amount),
            "balance": None if self.balance is None else str(self.balance),
            "direction": self.direction,
            "type": self.type,
            "counterparty": self.counterparty,
            "iban": self.iban,
            "reference": self.reference,
            "row": self.row,
        }


@dataclass
class Statement:
    transactions: list[Transaction]
    account_iban: str | None = None
    """IBAN printed above the table, if the export has one."""
    opening_balance: Decimal | None = None
    columns: dict[str, str] = field(default_factory=dict)
    """Which header in the file each field was read from."""

    def __iter__(self) -> Iterator[Transaction]:
        return iter(self.transactions)

    def __len__(self) -> int:
        return len(self.transactions)

    @property
    def total_in(self) -> Decimal:
        return sum((t.amount for t in self.transactions if t.amount > 0), Decimal(0))

    @property
    def total_out(self) -> Decimal:
        return sum((t.amount for t in self.transactions if t.amount < 0), Decimal(0))

    def summary(self) -> dict[str, object]:
        """Totals overall and per transaction type, with money as strings."""
        counts: dict[str, int] = {}
        money: dict[tuple[str, str], Decimal] = {}
        for t in self.transactions:
            counts[t.type] = counts.get(t.type, 0) + 1
            key = (t.type, t.direction)
            money[key] = money.get(key, Decimal(0)) + t.amount
        dates = [t.date for t in self.transactions]
        return {
            "count": len(self.transactions),
            "first_date": min(dates).isoformat() if dates else None,
            "last_date": max(dates).isoformat() if dates else None,
            "total_in": str(self.total_in),
            "total_out": str(self.total_out),
            "net": str(self.total_in + self.total_out),
            "account_iban": self.account_iban,
            "by_type": {
                name: {
                    "count": count,
                    "in": str(money.get((name, "in"), Decimal(0))),
                    "out": str(money.get((name, "out"), Decimal(0))),
                }
                for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            },
        }


# --- header detection -------------------------------------------------------


@dataclass(frozen=True)
class _Spec:
    keywords: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    exact_only: bool = False


# Order matters: a column taken by an earlier field is not offered to later
# ones. Specific headers ("Valör", "Bakiye", "B/A") are claimed first so the
# looser ones ("tarih", "tutar") cannot grab them.
_SPECS: dict[str, _Spec] = {
    "value_date": _Spec(("valor tarihi", "valor")),
    "balance": _Spec(("bakiye", "kalan bakiye", "islem sonrasi bakiye")),
    "indicator": _Spec(("b/a", "borc/alacak", "islem yonu", "yon", "ba"), exact_only=True),
    "debit": _Spec(("borc", "borc tutari", "cikan", "giden tutar", "cekilen")),
    "credit": _Spec(("alacak", "alacak tutari", "giren", "gelen tutar", "yatan")),
    "date": _Spec(("islem tarihi", "tarih", "tarih/saat", "islem zamani")),
    "amount": _Spec(("islem tutari", "tutar", "miktar")),
    "description": _Spec(("aciklama", "islem aciklamasi", "detay", "islem detayi")),
    "reference": _Spec(
        ("dekont no", "fis no", "islem no", "referans no", "evrak no", "dekont", "referans")
    ),
}


def _score(cell: str, spec: _Spec) -> int:
    if not cell or any(word in cell for word in spec.exclude):
        return 0
    best = 0
    for rank, keyword in enumerate(spec.keywords):
        bonus = len(spec.keywords) - rank
        if cell == keyword:
            best = max(best, 300 + bonus)
        elif spec.exact_only:
            continue
        elif cell.startswith(keyword):
            best = max(best, 200 + bonus)
        elif re.search(rf"\b{re.escape(keyword)}\b", cell):
            best = max(best, 100 + bonus)
    return best


def _map_header(row: Row) -> dict[str, int] | None:
    cells = [fold(c) for c in row]
    taken: set[int] = set()
    mapping: dict[str, int] = {}
    for name, spec in _SPECS.items():
        scores = [(_score(c, spec), -i, i) for i, c in enumerate(cells) if i not in taken]
        best = max(scores, default=(0, 0, -1))
        if best[0] > 0:
            mapping[name] = best[2]
            taken.add(best[2])
    has_money = "amount" in mapping or "debit" in mapping or "credit" in mapping
    if "date" in mapping and "description" in mapping and has_money:
        return mapping
    return None


def _find_header(sheet: Sheet, depth: int = 60) -> tuple[int, dict[str, int]] | None:
    for index, row in enumerate(sheet[:depth]):
        mapping = _map_header(row)
        if mapping:
            return index, mapping
    return None


# --- rows -------------------------------------------------------------------


def _cell(row: Row, mapping: dict[str, int], name: str) -> object:
    index = mapping.get(name)
    if index is None or index >= len(row):
        return None
    return row[index]


def _amount(row: Row, mapping: dict[str, int]) -> Decimal | None:
    if "amount" in mapping:
        amount = parse_amount(_cell(row, mapping, "amount"))
        if amount is None:
            return None
        indicator = fold(_cell(row, mapping, "indicator"))
        if indicator.startswith(("b", "-")):
            return -abs(amount)
        if indicator.startswith(("a", "+")):
            return abs(amount)
        return amount
    debit = parse_amount(_cell(row, mapping, "debit"))
    credit = parse_amount(_cell(row, mapping, "credit"))
    if debit is None and credit is None:
        return None
    return abs(credit or Decimal(0)) - abs(debit or Decimal(0))


def _transactions(
    sheet: Sheet, header: int, mapping: dict[str, int]
) -> tuple[list[Transaction], Decimal | None]:
    found: list[Transaction] = []
    opening: Decimal | None = None
    for index in range(header + 1, len(sheet)):
        row = sheet[index]
        when = parse_date(_cell(row, mapping, "date"))
        if when is None:
            continue  # totals, footers, page breaks and blank lines have no date
        description = clean(_cell(row, mapping, "description"))
        balance = parse_amount(_cell(row, mapping, "balance"))
        amount = _amount(row, mapping)
        if amount is None:
            if "devir" in fold(description) and balance is not None:
                opening = balance
            continue
        found.append(
            Transaction(
                date=when,
                description=description,
                amount=amount,
                balance=balance,
                value_date=parse_date(_cell(row, mapping, "value_date")),
                reference=clean(_cell(row, mapping, "reference")),
                type=classify(description),
                counterparty=find_counterparty(description),
                iban=find_iban(description),
                row=index + 1,
            )
        )
    return found, opening


def read(source: str | Path | bytes | BinaryIO) -> Statement:
    """Read a bank statement export (.xlsx, .xls, HTML-as-.xls or .csv).

    The transaction table is found by its header names, so title rows, account
    details above the table and footer notes below it do not matter.
    """
    if isinstance(source, bytes):
        data = source
    elif isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise StatementError(f"File not found: {path}")
        data = path.read_bytes()
    else:
        data = source.read()
    if not data.strip():
        raise StatementError("The file is empty.")

    for sheet in read_sheets(data):
        found = _find_header(sheet)
        if not found:
            continue
        header, mapping = found
        transactions, opening = _transactions(sheet, header, mapping)
        preamble = " ".join(clean(c) for row in sheet[:header] for c in row if c is not None)
        header_row = sheet[header]
        return Statement(
            transactions=transactions,
            account_iban=find_iban(preamble),
            opening_balance=opening,
            columns={name: clean(header_row[i]) for name, i in mapping.items()},
        )

    raise StatementError(
        "No transaction table found. ekstre looks for a header row with a date "
        "column (Tarih), a description column (Açıklama) and an amount column "
        "(Tutar, or Borç/Alacak)."
    )
