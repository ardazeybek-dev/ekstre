"""Builders for made-up statement files. No real names, accounts or IBANs."""

from __future__ import annotations

import io
from datetime import date, datetime

import pytest


def make_iban(bban: str) -> str:
    """Valid Turkish IBAN for a made-up 22-digit BBAN."""
    rearranged = bban + "TR00"
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return f"TR{98 - int(digits) % 97:02d}{bban}"


ACCOUNT_IBAN = make_iban("0001200000000000000001")
OTHER_IBAN = make_iban("0004600000000000000099")


def xlsx_bytes(rows: list[list[object]]) -> bytes:
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


@pytest.fixture
def single_amount_xlsx() -> bytes:
    """Signed amount column, numeric cells, title and footer rows around it."""
    return xlsx_bytes(
        [
            ["HESAP HAREKETLERİ"],
            ["Müşteri", "Deneme Kişi"],
            ["IBAN", ACCOUNT_IBAN],
            [],
            ["İŞLEM TARİHİ", "VALÖR", "AÇIKLAMA", "İŞLEM TUTARI", "BAKİYE", "DEKONT NO"],
            [
                datetime(2026, 11, 3, 9, 15),
                date(2026, 11, 3),
                "MAAŞ ÖDEMESİ KASIM",
                45000.0,
                46250.5,
                "A-1",
            ],
            [
                datetime(2026, 11, 4, 13, 2),
                date(2026, 11, 4),
                "POS SATIŞ ÖRNEK MARKET",
                -812.4,
                45438.1,
                "A-2",
            ],
            [
                datetime(2026, 11, 5),
                date(2026, 11, 5),
                f"FAST GİDEN ALICI: ÖRNEK İŞLETME LTD {OTHER_IBAN}",
                -1500,
                43938.1,
                "A-3",
            ],
            [None, None, "Toplam", 42687.6, None, None],
            ["Borç: 2.312,40", None, "Alacak: 45.000,00"],
            ["Bu belge bilgi amaçlıdır. www.ornekbanka.test"],
        ]
    )


@pytest.fixture
def debit_credit_xlsx() -> bytes:
    """Separate Borç/Alacak text columns; the value date comes first."""
    return xlsx_bytes(
        [
            ["Valör Tarihi", "İşlem Tarihi", "Açıklama", "Borç", "Alacak", "Bakiye"],
            ["01.10.2026", "01.10.2026", "HAVALE GÖNDEREN: DENEME KİŞİ", "", "1.250,00", "1250,00"],
            ["02.10.2026", "02.10.2026", "ATM PARA ÇEKME", "500,00", "", "750,00"],
            ["03.10.2026", "02.10.2026", "KREDİ KARTI ÖDEMESİ", "-300,25", "", "449,75"],
        ]
    )  # fmt: skip


@pytest.fixture
def csv_cp1254() -> bytes:
    """Semicolon CSV in the Windows Turkish code page, trailing-minus amounts."""
    text = (
        "Hesap Hareketleri;;;\r\n"
        "Tarih;Açıklama;Tutar;Bakiye\r\n"
        "31.12.2025;DEVİR;;10.000,00\r\n"
        "02.01.2026;ELEKTRİK FATURASI OTOMATİK ÖDEME;845,30-;9.154,70\r\n"
        "03.01.2026;EFT GELEN KİMDEN: ÖRNEK ŞİRKET A.Ş.;2.000,00;11.154,70\r\n"
        "03.01.2026;EFT ÜCRETİ;6,50-;11.148,20\r\n"
    )
    return text.encode("cp1254")
