"""Testy logiki tokenów na poziomie funkcji db.py — bez HTTP, bez wątków."""

import test_wiedzy_app as app_module
from conftest import PYTANIA_TESTOWE

import db


def test_token_da_sie_zuzyc_tylko_raz(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    pierwszy_wynik = app_module.waliduj_i_zuzyj_token(token)
    drugi_wynik = app_module.waliduj_i_zuzyj_token(token)

    assert pierwszy_wynik == test_z_pytaniami
    assert drugi_wynik is None


def test_nieistniejacy_token_zwraca_none(klient):
    assert app_module.waliduj_i_zuzyj_token("COSCOSCOS") is None


def test_tokeny_generowane_w_partii_sa_unikalne(klient, test_z_pytaniami):
    nowe = db.wygeneruj_tokeny(test_z_pytaniami, 50, dlugosc=4)
    tokeny = [w["token"] for w in nowe]
    assert len(tokeny) == len(set(tokeny))


def test_dwa_testy_moga_miec_wspolne_tokeny_bez_kolizji(klient):
    test_id_1, _, _ = db.importuj_test_z_dataframe("Test 1", PYTANIA_TESTOWE.copy(), liczba_pytan=3)
    test_id_2, _, _ = db.importuj_test_z_dataframe("Test 2", PYTANIA_TESTOWE.copy(), liczba_pytan=3)

    tokeny_1 = {w["token"] for w in db.wygeneruj_tokeny(test_id_1, 30, dlugosc=4)}
    tokeny_2 = {w["token"] for w in db.wygeneruj_tokeny(test_id_2, 30, dlugosc=4)}

    assert tokeny_1.isdisjoint(tokeny_2)
