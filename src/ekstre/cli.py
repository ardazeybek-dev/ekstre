"""Command line: ``ekstre statement.xlsx`` prints clean CSV, JSON or a table."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from . import __version__
from .classify import TYPES
from .errors import StatementError
from .statement import Statement, Transaction, read

COLUMNS = (
    "date",
    "value_date",
    "description",
    "amount",
    "balance",
    "direction",
    "type",
    "counterparty",
    "iban",
    "reference",
    "row",
)


def _money(value: Decimal | str) -> str:
    return f"{Decimal(value):,.2f}"


def _short(text: str | None, width: int) -> str:
    text = text or ""
    return text if len(text) <= width else text[: width - 1] + "…"


def _as_csv(items: list[Transaction]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for t in items:
        writer.writerow(t.to_dict())
    return out.getvalue()


def _as_table(items: list[Transaction]) -> str:
    lines = [f"{'date':<10}  {'amount':>14}  {'type':<12}  {'description':<48}  counterparty"]
    for t in items:
        lines.append(
            f"{t.date.isoformat():<10}  {_money(t.amount):>14}  {t.type:<12}  "
            f"{_short(t.description, 48):<48}  {t.counterparty or ''}".rstrip()
        )
    return "\n".join(lines) + "\n"


def _summary_text(statement: Statement) -> str:
    s = statement.summary()
    lines = [f"{s['count']} transactions"]
    if s["first_date"]:
        lines[0] += f", {s['first_date']} to {s['last_date']}"
    if s["account_iban"]:
        lines.append(f"Account: {s['account_iban']}")
    lines += [
        f"In:  {_money(s['total_in']):>16}",  # type: ignore[arg-type]
        f"Out: {_money(s['total_out']):>16}",  # type: ignore[arg-type]
        f"Net: {_money(s['net']):>16}",  # type: ignore[arg-type]
        "",
        f"{'type':<12}  {'count':>5}  {'in':>14}  {'out':>14}",
    ]
    by_type: dict[str, dict[str, str]] = s["by_type"]  # type: ignore[assignment]
    for name, v in by_type.items():
        lines.append(f"{name:<12}  {v['count']:>5}  {_money(v['in']):>14}  {_money(v['out']):>14}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ekstre",
        description=(
            "Read a Turkish bank statement export (.xlsx, .xls or .csv) and print "
            "clean, typed transactions."
        ),
    )
    parser.add_argument("file", type=Path, help="statement file downloaded from online banking")
    parser.add_argument(
        "-f",
        "--format",
        choices=("csv", "json", "table"),
        default="csv",
        help="output format (default: csv)",
    )
    parser.add_argument("-o", "--output", type=Path, help="write to this file instead of stdout")
    parser.add_argument(
        "-s", "--summary", action="store_true", help="print totals per transaction type instead"
    )
    parser.add_argument(
        "-t",
        "--type",
        action="append",
        choices=TYPES,
        metavar="TYPE",
        help=f"keep only this type; repeatable. One of: {', '.join(TYPES)}",
    )
    parser.add_argument("-V", "--version", action="version", version=f"ekstre {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        statement = read(args.file)
    except StatementError as error:
        print(f"ekstre: {error}", file=sys.stderr)
        return 1

    items = [t for t in statement if not args.type or t.type in args.type]
    if args.type:
        statement = Statement(items, statement.account_iban, statement.opening_balance)

    if args.summary:
        text = (
            json.dumps(statement.summary(), ensure_ascii=False, indent=2) + "\n"
            if args.format == "json"
            else _summary_text(statement)
        )
    elif args.format == "json":
        text = json.dumps([t.to_dict() for t in items], ensure_ascii=False, indent=2) + "\n"
    elif args.format == "table":
        text = _as_table(items)
    else:
        text = _as_csv(items)

    if args.output:
        # utf-8-sig so Excel opens the CSV with Turkish letters intact.
        encoding = "utf-8-sig" if args.format == "csv" and not args.summary else "utf-8"
        args.output.write_text(text, encoding=encoding, newline="")
        print(f"ekstre: {len(items)} transactions written to {args.output}", file=sys.stderr)
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
