import io
import re
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from conftest import ACCOUNT_IBAN, OTHER_IBAN, xlsx_bytes

from ekstre import StatementError, read


def test_single_amount_column(single_amount_xlsx):
    statement = read(single_amount_xlsx)
    assert len(statement) == 3  # the total and footer rows are not transactions
    salary, pos, fast = statement
    assert salary.date == date(2026, 11, 3)
    assert salary.amount == Decimal("45000.0")
    assert salary.type == "salary"
    assert salary.reference == "A-1"
    assert salary.row == 6
    assert pos.amount == Decimal("-812.4")
    assert pos.direction == "out"
    assert pos.balance == Decimal("45438.1")
    assert fast.type == "fast"
    assert fast.counterparty == "ÖRNEK İŞLETME LTD"
    assert fast.iban == OTHER_IBAN
    assert statement.account_iban == ACCOUNT_IBAN
    assert statement.columns["amount"] == "İŞLEM TUTARI"


def test_debit_credit_columns_and_value_date_first(debit_credit_xlsx):
    statement = read(debit_credit_xlsx)
    assert [t.amount for t in statement] == [
        Decimal("1250.00"),
        Decimal("-500.00"),
        Decimal("-300.25"),  # a debit written as negative is still a debit
    ]
    card = statement.transactions[2]
    assert card.date == date(2026, 10, 2)  # İşlem Tarihi, not the Valör column
    assert card.value_date == date(2026, 10, 3)
    assert statement.transactions[0].counterparty == "DENEME KİŞİ"
    assert statement.columns["date"] == "İşlem Tarihi"


def test_cp1254_semicolon_csv(csv_cp1254):
    statement = read(csv_cp1254)
    assert statement.opening_balance == Decimal("10000.00")
    assert [(t.type, t.amount) for t in statement] == [
        ("bill", Decimal("-845.30")),
        ("eft", Decimal("2000.00")),
        ("fee", Decimal("-6.50")),
    ]
    assert statement.transactions[1].counterparty == "ÖRNEK ŞİRKET A.Ş."
    assert statement.total_in == Decimal("2000.00")
    assert statement.total_out == Decimal("-851.80")


def test_utf8_csv_with_bom_and_indicator_column():
    text = (
        "İşlem Tarihi;Açıklama;Tutar;B/A\n"
        "05.03.2026;POS ALIŞVERİŞ;120,00;B\n"
        "06.03.2026;FAST GELEN;80,00;A\n"
    )
    statement = read(("﻿" + text).encode("utf-8"))
    assert [t.amount for t in statement] == [Decimal("-120.00"), Decimal("80.00")]


def test_html_disguised_as_xls():
    html = """<html><head><meta charset="utf-8"></head><body>
    <table><tr><td colspan="3">Hesap Özeti</td></tr></table>
    <table>
      <tr><th>Tarih</th><th>Açıklama</th><th>Tutar</th><th>Bakiye</th></tr>
      <tr><td>10.02.2026</td><td>HAVALE<br>GELEN</td><td>1.000,00</td><td>1.000,00</td></tr>
      <tr><td>11.02.2026</td><td>ATM PARA ÇEKME</td><td>-200,00</td><td>800,00</td></tr>
    </table></body></html>"""
    statement = read(html.encode("utf-8"))
    assert [(t.description, t.amount) for t in statement] == [
        ("HAVALE GELEN", Decimal("1000.00")),
        ("ATM PARA ÇEKME", Decimal("-200.00")),
    ]


def test_legacy_xls():
    xlwt = pytest.importorskip("xlwt")
    book = xlwt.Workbook()
    sheet = book.add_sheet("Hareketler")
    date_style = xlwt.easyxf(num_format_str="DD.MM.YYYY")
    for col, title in enumerate(["Tarih", "Açıklama", "Tutar"]):
        sheet.write(0, col, title)
    sheet.write(1, 0, date(2026, 4, 1), date_style)
    sheet.write(1, 1, "EFT GELEN")
    sheet.write(1, 2, 250.75)
    out = io.BytesIO()
    book.save(out)

    (only,) = read(out.getvalue())
    assert only.date == date(2026, 4, 1)
    assert only.amount == Decimal("250.75")
    assert only.type == "eft"


def test_header_on_second_sheet():
    import openpyxl

    book = openpyxl.Workbook()
    book.active.append(["Kapak sayfası"])
    data = book.create_sheet("Hareketler")
    data.append(["Tarih", "Açıklama", "Tutar"])
    data.append(["01.01.2026", "FAST GELEN", "5,00"])
    out = io.BytesIO()
    book.save(out)
    assert len(read(out.getvalue())) == 1


def test_workbook_with_styles_openpyxl_rejects():
    data = xlsx_bytes([["Tarih", "Açıklama", "Tutar"], ["01.01.2026", "EFT GELEN", "5,00"]])
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            content = src.read(item.filename)
            if item.filename == "xl/styles.xml":
                # A fill element openpyxl cannot build, as some exporters write.
                content = re.sub(
                    rb"<fills[^>]*>.*?</fills>",
                    b'<fills count="2"><fill><bogusFill/></fill><fill><bogusFill/></fill></fills>',
                    content,
                    flags=re.DOTALL,
                )
            dst.writestr(item, content)
    assert len(read(out.getvalue())) == 1


def test_read_from_path_and_file_object(tmp_path, csv_cp1254):
    path = tmp_path / "ekstre.csv"
    path.write_bytes(csv_cp1254)
    assert len(read(path)) == 3
    assert len(read(str(path))) == 3
    assert len(read(io.BytesIO(csv_cp1254))) == 3


def test_summary(csv_cp1254):
    summary = read(csv_cp1254).summary()
    assert summary["count"] == 3
    assert summary["first_date"] == "2026-01-02"
    assert summary["net"] == "1148.20"
    assert summary["by_type"]["eft"] == {"count": 1, "in": "2000.00", "out": "0"}


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "empty"),
        (b"Ad;Soyad\nDeneme;Kisi\n", "No transaction table"),
        (b"<html><body>no table</body></html>", "no table"),
        (b"\xd0\xcf\x11\xe0broken", "xls"),
    ],
)
def test_errors(data, message):
    with pytest.raises(StatementError, match=message):
        read(data)


def test_missing_file(tmp_path):
    with pytest.raises(StatementError, match="not found"):
        read(tmp_path / "yok.xlsx")
