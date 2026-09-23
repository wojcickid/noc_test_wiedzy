"""Testy Etapu 2 (patrz PLAN_POPRAWEK.md): postęp testu w tabeli `podejscia`,
wznowienie tym samym tokenem (B1, B9, E13), UNIQUE(token, pytanie_id) (B8),
mianownik wyniku z liczby wylosowanych pytań (L3), reset tokenu przez admina
(L2), statusy tokenów w panelu (UI8) i migracja historycznych danych."""

import json
import re
import sqlite3

import pytest

import db
import test_wiedzy_app as app_module
from conftest import pobierz_csrf_token, zaloguj_admina
from pomocnicze import przejdz_caly_test


# --- B1/E13: wznowienie tym samym tokenem, także na innym urządzeniu ---------------------

def test_wznowienie_na_innym_urzadzeniu_kontynuuje_od_tego_samego_pytania(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    start = klient.post("/", data={"token": token}, follow_redirects=True)
    pytanie_id = re.search(rb'name="pytanie_id" value="(\d+)"', start.data).group(1).decode()
    klient.post("/test", data={"pytanie_id": pytanie_id, "odpowiedz": "B"}, follow_redirects=True)

    # Nowy klient testowy = nowe ciasteczko sesji, czyli symulacja innej przeglądarki/urządzenia.
    with app_module.app.test_client() as inny_klient:
        wznowienie = inny_klient.post("/", data={"token": token}, follow_redirects=True)
        assert b"Pytanie 2 z 3" in wznowienie.data


# --- B9: podwójne kliknięcie "Rozpocznij test" wznawia zamiast fałszywego błędu ----------

def test_podwojne_kliknieciu_rozpocznij_wznawia_zamiast_bledu(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    pierwszy = klient.post("/", data={"token": token}, follow_redirects=True)
    drugi = klient.post("/", data={"token": token}, follow_redirects=True)

    assert b"Pytanie 1 z 3" in pierwszy.data
    assert b"Pytanie 1 z 3" in drugi.data
    assert "Nieprawidłowy lub już wykorzystany".encode("utf-8") not in drugi.data


# --- B8: podwójne wysłanie ostatniej odpowiedzi ("Zakończ test") nie duplikuje wpisu -----

def test_podwojne_wyslanie_ostatniej_odpowiedzi_nie_duplikuje_wpisu(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    strona = klient.post("/", data={"token": token}, follow_redirects=True)
    for _ in range(2):
        pytanie_id = re.search(rb'name="pytanie_id" value="(\d+)"', strona.data).group(1).decode()
        strona = klient.post("/test", data={"pytanie_id": pytanie_id, "odpowiedz": "B"}, follow_redirects=True)

    ostatnie_id = re.search(rb'name="pytanie_id" value="(\d+)"', strona.data).group(1).decode()
    klient.post("/test", data={"pytanie_id": ostatnie_id, "odpowiedz": "B"}, follow_redirects=False)
    powtorka = klient.post("/test", data={"pytanie_id": ostatnie_id, "odpowiedz": "B"}, follow_redirects=True)

    assert b"Poprawne odpowiedzi: 3" in powtorka.data
    with db.baza() as conn:
        liczba = conn.execute(
            "SELECT COUNT(*) AS c FROM odpowiedzi_uzytkownika WHERE token = ?", (token,)
        ).fetchone()["c"]
    assert liczba == 3


def test_unikalny_indeks_blokuje_duplikat_odpowiedzi_na_poziomie_bazy(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    with db.baza() as conn:
        pytanie_id = conn.execute(
            "SELECT id FROM pytania WHERE test_id = ? LIMIT 1", (test_z_pytaniami,)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO odpowiedzi_uzytkownika (token, pytanie_id, odpowiedz, data_wyslania) VALUES (?, ?, 'B', '2026-01-01 00:00:00')",
            (token, pytanie_id),
        )

    with pytest.raises(sqlite3.IntegrityError):
        with db.baza() as conn:
            conn.execute(
                "INSERT INTO odpowiedzi_uzytkownika (token, pytanie_id, odpowiedz, data_wyslania) VALUES (?, ?, 'A', '2026-01-01 00:00:01')",
                (token, pytanie_id),
            )


# --- S: token w trakcie testu nie ujawnia cząstkowych wyników przez /sprawdz-wynik -------

def test_sprawdz_wynik_nie_pokazuje_czesciowych_wynikow_w_trakcie_testu(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    start = klient.post("/", data={"token": token}, follow_redirects=True)
    pytanie_id = re.search(rb'name="pytanie_id" value="(\d+)"', start.data).group(1).decode()
    klient.post("/test", data={"pytanie_id": pytanie_id, "odpowiedz": "B"}, follow_redirects=True)

    odpowiedz = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert "Nie znaleziono wyników dla podanego tokenu".encode("utf-8") in odpowiedz.data


# --- L2: reset tokenu przez admina usuwa poprzednie odpowiedzi i pozwala zacząć od nowa --

def test_reset_tokenu_pozwala_zaczac_od_nowa(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    with app_module.app.test_client() as uczestnik:
        przejdz_caly_test(uczestnik, token, litera_odpowiedzi="B")

    odpowiedz = klient.post(
        f"/admin/tokeny/{token}/reset",
        data={"test_id": str(test_z_pytaniami), "csrf_token": pobierz_csrf_token(klient)},
        follow_redirects=True,
    )
    assert f"Token {token} został zresetowany".encode("utf-8") in odpowiedz.data

    with db.baza() as conn:
        liczba_odpowiedzi = conn.execute(
            "SELECT COUNT(*) AS c FROM odpowiedzi_uzytkownika WHERE token = ?", (token,)
        ).fetchone()["c"]
        liczba_podejsc = conn.execute(
            "SELECT COUNT(*) AS c FROM podejscia WHERE token = ?", (token,)
        ).fetchone()["c"]
    assert liczba_odpowiedzi == 0
    assert liczba_podejsc == 0

    with app_module.app.test_client() as uczestnik2:
        wynik = przejdz_caly_test(uczestnik2, token, litera_odpowiedzi="A")
    assert b"Poprawne odpowiedzi: 0" in wynik.data


def test_reset_nieistniejacego_tokenu_pokazuje_blad(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post(
        "/admin/tokeny/NIEISTNIEJACY/reset",
        data={"test_id": str(test_z_pytaniami), "csrf_token": pobierz_csrf_token(klient)},
        follow_redirects=True,
    )
    assert "Nie znaleziono tokenu.".encode("utf-8") in odpowiedz.data


# --- UI8: statusy tokenów w panelu (wolny / w trakcie / ukończony) -----------------------

def test_status_tokenow_w_panelu(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    tokeny = db.wygeneruj_tokeny(test_z_pytaniami, 3, dlugosc=6)
    wolny, w_trakcie, zakonczony = [w["token"] for w in tokeny]

    with app_module.app.test_client() as c:
        c.post("/", data={"token": w_trakcie}, follow_redirects=True)
    with app_module.app.test_client() as c:
        przejdz_caly_test(c, zakonczony)

    strona = klient.get(f"/admin/testy/{test_z_pytaniami}/tokeny")
    assert b"wolny" in strona.data
    assert "w trakcie".encode("utf-8") in strona.data
    assert "ukończony".encode("utf-8") in strona.data


# --- L3: mianownik wyniku to liczba wylosowanych pytań, nie COUNT() odpowiedzi -----------

def test_zbiorcze_wyniki_licza_mianownik_z_liczby_wylosowanych_pytan(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    with db.baza() as conn:
        pytania_id = [
            w["id"] for w in conn.execute("SELECT id FROM pytania WHERE test_id = ?", (test_z_pytaniami,)).fetchall()
        ]
        conn.execute(
            """
            INSERT INTO podejscia
                (token, test_id, wybrane_pytania, liczba_pytan, indeks_pytania, status, data_rozpoczecia, data_zakonczenia)
            VALUES (?, ?, ?, ?, ?, 'zakonczone', '2026-01-01 00:00:00', '2026-01-01 00:05:00')
            """,
            (token, test_z_pytaniami, json.dumps(pytania_id), len(pytania_id), len(pytania_id)),
        )
        # Celowo zapisujemy tylko jedną odpowiedź, żeby mianownik z COUNT() dałby błędny wynik.
        conn.execute(
            "INSERT INTO odpowiedzi_uzytkownika (token, pytanie_id, odpowiedz, data_wyslania) VALUES (?, ?, 'B', '2026-01-01 00:01:00')",
            (token, pytania_id[0]),
        )
        wiersz = conn.execute("SELECT * FROM zbiorcze_wyniki WHERE token = ?", (token,)).fetchone()

    assert wiersz["wszystkie"] == len(pytania_id)
    assert wiersz["poprawne"] == 1


# --- Migracja: historyczne odpowiedzi sprzed tabeli `podejscia` dostają wiersz -----------

def test_migracja_odtwarza_podejscia_dla_historycznych_odpowiedzi(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    with db.baza() as conn:
        pytania_id = [
            w["id"] for w in conn.execute("SELECT id FROM pytania WHERE test_id = ?", (test_z_pytaniami,)).fetchall()
        ]
        for pid in pytania_id:
            conn.execute(
                "INSERT INTO odpowiedzi_uzytkownika (token, pytanie_id, odpowiedz, data_wyslania) VALUES (?, ?, 'B', '2026-01-01 00:00:00')",
                (token, pid),
            )
        conn.execute(
            "UPDATE tokeny SET wykorzystany = 1, data_wykorzystania = '2026-01-01 00:00:00' WHERE token = ?",
            (token,),
        )

    db.inicjalizuj()  # symuluje ponowne uruchomienie appki po wgraniu Etapu 2

    with db.baza() as conn:
        podejscie = conn.execute("SELECT * FROM podejscia WHERE token = ?", (token,)).fetchone()
    assert podejscie is not None
    assert podejscie["status"] == "zakonczone"
    assert podejscie["liczba_pytan"] == len(pytania_id)


# --- L1: mechanizm plikowej sesji uczestnika został usunięty -----------------------------

def test_mechanizm_plikowej_sesji_zostal_usuniety():
    assert not hasattr(app_module, "get_server_session")
    assert not hasattr(app_module, "save_server_session")
    assert not hasattr(app_module, "clear_server_session")
    assert not hasattr(app_module, "SESSION_DIR")
