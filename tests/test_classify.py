import pytest
from conftest import OTHER_IBAN

from ekstre import classify, find_counterparty, find_iban, iban_is_valid


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("FAST GELEN - GÖNDEREN: DENEME KİŞİ", "fast"),
        ("EFT GİDEN ÖRNEK ŞİRKET", "eft"),
        ("Havale - Kira", "havale"),
        ("POS SATIŞ ÖRNEK MARKET", "pos"),
        ("İnternet alışveriş", "pos"),
        ("ATM PARA ÇEKME", "atm"),
        ("Bankamatik nakit çekim", "atm"),
        ("KREDİ KARTI ÖDEMESİ", "card_payment"),
        ("KK ÖDEME 1234", "card_payment"),
        ("ELEKTRİK FATURASI OTOMATİK ÖDEME", "bill"),
        ("MAAŞ ÖDEMESİ KASIM", "salary"),
        ("FAST MAAŞ ÖDEMESİ", "salary"),
        ("EFT ÜCRETİ", "fee"),
        ("Hesap işletim ücreti", "fee"),
        ("MTV ÖDEMESİ", "tax"),
        ("VADELİ HESAP FAİZ", "interest"),
        ("POSTA ÇEKİ", "other"),
        ("KASIM MAAŞI", "salary"),
        ("ARALIK DÖNEMİ SU FATURASI", "bill"),
        ("VADELİ HESAP FAİZİ", "interest"),
        ("KİRA HAVALESİ", "havale"),
        ("ATM'DEN PARA ÇEKİLDİ", "atm"),
        ("İŞLEM MASRAFI", "fee"),
        ("HARCAMA İADESİ", "pos"),
        ("TAPU HARCI", "tax"),
        ("", "other"),
    ],
)
def test_classify(description, expected):
    assert classify(description) == expected


def test_iban_checksum():
    assert iban_is_valid(OTHER_IBAN)
    broken = OTHER_IBAN[:-1] + str((int(OTHER_IBAN[-1]) + 1) % 10)
    assert not iban_is_valid(broken)
    assert not iban_is_valid("TR12")


def test_find_iban_with_spaces():
    spaced = " ".join([OTHER_IBAN[:4]] + [OTHER_IBAN[i : i + 4] for i in range(4, 26, 4)])
    assert find_iban(f"Alıcı hesap {spaced} kira") == OTHER_IBAN


def test_find_iban_ignores_invalid():
    assert find_iban("TR000000000000000000000000") is None


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("FAST GELEN GÖNDEREN: DENEME KİŞİ", "DENEME KİŞİ"),
        ("EFT GİDEN ALICI: ÖRNEK LTD / KİRA", "ÖRNEK LTD"),
        (f"FAST ALICI ADI: ÖRNEK İŞLETME {OTHER_IBAN}", "ÖRNEK İŞLETME"),
        ("GONDEREN=Deneme Kişi, açıklama: aidat", "Deneme Kişi"),
        ("POS SATIŞ ÖRNEK MARKET", None),
    ],
)
def test_find_counterparty(description, expected):
    assert find_counterparty(description) == expected
