# ekstre

[![CI](https://github.com/ardazeybek-dev/ekstre/actions/workflows/ci.yml/badge.svg)](https://github.com/ardazeybek-dev/ekstre/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ekstre.svg)](https://pypi.org/project/ekstre/)
[![Python](https://img.shields.io/pypi/pyversions/ekstre.svg)](https://pypi.org/project/ekstre/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Read the account statement (*hesap hareketleri / ekstre*) you download from
Turkish online banking and get clean, typed transactions: signed amounts,
real dates, the transaction type (FAST, EFT, POS, ATM, salary, bill, …),
the counterparty and any IBAN in the description.

```console
$ ekstre hesap-hareketleri.xlsx -f table
date                amount  type          description                                       counterparty
2026-11-03       45,000.00  salary        MAAŞ ÖDEMESİ KASIM
2026-11-04         -812.40  pos           POS SATIŞ ÖRNEK MARKET
2026-11-05       -1,500.00  fast          FAST GİDEN ALICI: ÖRNEK İŞLETME LTD TR360004600…  ÖRNEK İŞLETME LTD
```

## Why

Every bank exports a slightly different file, and all of them get in the way
of a script:

- the table starts on row 8, under the bank logo and account details, and is
  followed by totals and legal notes;
- amounts are text like `1.250,00-` or `(75,50)`, or split into separate
  *Borç* and *Alacak* columns, or come with a `B/A` flag;
- the `.xls` file is often an HTML page with a different extension, and the
  `.csv` is `;`-separated and encoded in Windows-1254;
- headers are upper case (`İŞLEM TUTARI`), which Python's `str.lower()` does
  not fold correctly, so a naive `"açıklama" in header.lower()` fails.

`ekstre` deals with all of that and hands you one list of transactions.

## How it reads a file

ekstre is a **header-based general reader**, not a collection of per-bank
templates. It scans the first rows for a header that has a date column
(*Tarih*, *İşlem Tarihi*), a description column (*Açıklama*) and money
(*Tutar*, or *Borç*/*Alacak*), and reads every row below it that starts with
a date. Rows without a date (totals, footers, page breaks) are skipped.

It has been tested against made-up files in the layouts above. It has not yet
been checked against a real export from each bank, so no bank is listed as
supported. If your bank's file is not read correctly, open an issue with the
header row and one anonymised line.

## Installation

```bash
pip install ekstre            # .xlsx, .csv and HTML ".xls"
pip install "ekstre[xls]"     # also old binary .xls workbooks
```

Requires Python 3.10 or newer. The only dependency is `openpyxl`.

## Command line

```bash
ekstre statement.xlsx                    # CSV to stdout
ekstre statement.xlsx -o clean.csv       # CSV file that Excel opens with Turkish letters intact
ekstre statement.xlsx -f json            # JSON list
ekstre statement.xlsx -f table           # readable table
ekstre statement.xlsx --summary          # totals in / out / net, per type
ekstre statement.xlsx -t pos -t atm      # only card spending and cash withdrawals
```

`python -m ekstre` works too. The exit code is 1 when the file cannot be read,
with the reason on stderr.

## Library

```python
import ekstre

statement = ekstre.read("statement.xlsx")      # path, bytes or a binary file object

for t in statement:
    print(t.date, t.amount, t.type, t.counterparty, t.iban)

statement.total_in        # Decimal('45000.0')
statement.total_out       # Decimal('-2312.4')
statement.account_iban    # IBAN printed above the table, if any
statement.summary()       # dict, money as strings
[t.to_dict() for t in statement]   # JSON-ready rows
```

Money is `Decimal`, never `float`. Amounts are negative for money going out.

Each `Transaction` has `date`, `description`, `amount`, `balance`,
`value_date`, `reference`, `type`, `counterparty`, `iban`, `direction`
(`"in"`/`"out"`) and `row` (the line number in the source file).

The building blocks are public as well:

```python
ekstre.parse_amount("1.250,00-")                 # Decimal('-1250.00')
ekstre.parse_date("03.11.2026 14:32")            # datetime.date(2026, 11, 3)
ekstre.classify("KİRA HAVALESİ")                 # 'havale'
ekstre.find_iban("ALICI TR33 0006 1005 1978 6457 8413 26")  # 'TR330006100519786457841326'
ekstre.fold("İŞLEM TUTARI")                      # 'islem tutari'
```

### Transaction types

| type           | matched on (examples)                                  |
| -------------- | ------------------------------------------------------ |
| `salary`       | maaş, ücret ödemesi                                    |
| `card_payment` | kredi kartı, kart borcu, KK                            |
| `bill`         | fatura, otomatik ödeme, elektrik, doğalgaz             |
| `tax`          | vergi, SGK, MTV, harç, BSMV                            |
| `interest`     | faiz, getiri                                           |
| `fee`          | komisyon, masraf, … ücreti, hesap işletim              |
| `atm`          | ATM, bankamatik, nakit çekim, para yatırma             |
| `pos`          | POS, alışveriş, harcama                                |
| `fast` / `eft` / `havale` | the transfer channel                        |
| `other`        | none of the above                                      |

The first match wins and purpose beats channel, so `FAST MAAŞ ÖDEMESİ` is
`salary`. A counterparty is only returned when the bank labelled it
(`GÖNDEREN:`, `ALICI:`, `KARŞI TARAF:`, `KİMDEN:`); otherwise it is `None`
rather than a guess. IBANs are checked with the mod-97 checksum.

## Development

```bash
pip install -e ".[dev]"
pytest              # unit tests and doctests
ruff check . && ruff format --check .
```

Test files are generated inside the tests with invented names and IBANs. Do
not commit real statements; `.gitignore` blocks spreadsheet files for that
reason.

```
src/ekstre/
  statement.py   header detection, Transaction, Statement, read()
  files.py       xlsx / xls / HTML / csv to rows, decided by the file's bytes
  parse.py       Turkish case folding, amounts, dates
  classify.py    transaction type, IBAN, counterparty
  cli.py         the ekstre command
tests/           pytest suite; conftest.py builds the sample files
```

Releases go to PyPI from GitHub through trusted publishing: publishing a
GitHub release runs `.github/workflows/publish.yml`.

## Pitfalls

- Header match fails on upper-case Turkish → `str.lower()` turns `I` into `i`
  and `İ` into `i̇` → compare through `ekstre.fold()`.
- `1.250` is read as one thousand two hundred fifty, because Turkish exports
  write decimals with a comma. A dot followed by one or two digits is a decimal.

## Related

[`trkit`](https://github.com/ardazeybek-dev/trkit) (Python) and
[`@ardazeybek-dev/trkit`](https://github.com/ardazeybek-dev/trkit-js) (npm):
Turkish case conversion, slugify, TCKN, IBAN and plate validators.

## License

MIT
