"""Testy poprawek z Etapu 1 (patrz PLAN_POPRAWEK.md): CSRF, open redirect, PRG przy
tokenach, walidacja odpowiedzi/test_id, test bez pytań, zakres wyników po test_id."""

import re

import pytest

import db
from conftest import PYTANIA_TESTOWE, pobierz_csrf_token, zaloguj_admina
from pomocnicze import przejdz_caly_test


# --- B2: open redirect przy logowaniu -----------------------------------------------

def test_login_ignoruje_zewnetrzny_adres_w_nastepny(klient, haslo_admina):
    odpowiedz = klient.post(
        "/admin/login?nastepny=https://zla-strona.pl/",
        data={"haslo": haslo_admina},
    )
    assert odpowiedz.status_code == 302
    assert odpowiedz.headers["Location"] == "/admin"


def test_login_honoruje_bezpieczny_adres_w_nastepny(klient, haslo_admina, test_z_pytaniami):
    cel = f"/admin/testy/{test_z_pytaniami}"
    odpowiedz = klient.post(f"/admin/login?nastepny={cel}", data={"haslo": haslo_admina})
    assert odpowiedz.headers["Location"] == cel


# --- B3/S3: CSRF na formularzach panelu admina ----------------------------------------

def test_post_bez_csrf_tokenu_jest_odrzucany(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post("/admin/import/przyklad")
    assert odpowiedz.status_code == 400


def test_post_z_bledym_csrf_tokenem_jest_odrzucany(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post("/admin/import/przyklad", data={"csrf_token": "zly-token"})
    assert odpowiedz.status_code == 400


def test_post_z_poprawnym_csrf_tokenem_dziala(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post(
        "/admin/import/przyklad", data={"csrf_token": pobierz_csrf_token(klient)}, follow_redirects=True
    )
    assert "Przykładowy test".encode("utf-8") in odpowiedz.data


# --- B7: walidacja odpowiedzi w /test ---------------------------------------------------

def test_nieprawidlowa_litera_odpowiedzi_nie_przechodzi_dalej(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    start = klient.post("/test", data={"start": "1"}, follow_redirects=True)
    pytanie_id = re.search(rb'name="pytanie_id" value="(\d+)"', start.data).group(1).decode()

    odpowiedz = klient.post("/test", data={"pytanie_id": pytanie_id, "odpowiedz": "Z"}, follow_redirects=True)
    assert "Zaznacz odpowiedź, aby przejść dalej.".encode("utf-8") in odpowiedz.data
    assert b"Pytanie 1 z 3" in odpowiedz.data


# --- B14: niezgodność pytanie_id (np. cofnięcie w przeglądarce) --------------------------

def test_niezgodny_pytanie_id_pokazuje_osobny_komunikat(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    klient.post("/test", data={"start": "1"}, follow_redirects=True)

    odpowiedz = klient.post("/test", data={"pytanie_id": "999999", "odpowiedz": "B"}, follow_redirects=True)
    assert "To pytanie zostało już zapisane".encode("utf-8") in odpowiedz.data


# --- B12: test bez żadnych pytań nie zapętla przekierowań -------------------------------

def test_test_bez_pytan_nie_zapetla_i_pokazuje_komunikat(klient):
    with db.baza() as conn:
        cur = conn.execute(
            "INSERT INTO testy (nazwa, data_importu, liczba_pytan_do_losowania) VALUES (?, ?, ?)",
            ("Pusty test", "2026-01-01 00:00:00", 20),
        )
        test_id = cur.lastrowid
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_id, 1, dlugosc=6)]

    klient.post("/", data={"token": token}, follow_redirects=True)
    odpowiedz = klient.post("/test", data={"start": "1"}, follow_redirects=True)
    assert "nie ma jeszcze żadnych pytań".encode("utf-8") in odpowiedz.data


# --- B11: zbyt mała pula kodów dla żądanej liczby tokenów podnosi czytelny błąd ----------

def test_zbyt_mala_pula_tokenow_podnosi_czytelny_blad(klient, test_z_pytaniami, monkeypatch):
    # Sztucznie mały alfabet (2 znaki, długość 4 => tylko 16 możliwych kodów),
    # żeby żądanie 40 tokenów szybko i deterministycznie wyczerpało pulę.
    monkeypatch.setattr(db, "ALFABET_KODOW", "AB")
    with pytest.raises(ValueError, match="zbyt mała pula"):
        db.wygeneruj_tokeny(test_z_pytaniami, 40, dlugosc=4)


# --- B15: nieliczbowy test_id przy przypisywaniu tokenu nie wywala 500 -------------------

def test_przypisz_z_nieliczbowym_test_id_nie_wywala_500(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    odpowiedz = klient.post(
        f"/admin/tokeny/{token}/przypisz",
        data={"przypisany": "X", "test_id": "abc", "csrf_token": pobierz_csrf_token(klient)},
    )
    assert odpowiedz.status_code == 302
    assert odpowiedz.headers["Location"] == "/admin"


# --- B16: wyniki na stronie testu są liczone po test_id, nie po nazwie -------------------

def test_wyniki_testu_sa_poprawnie_przypisane_do_test_id(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    test_id_1, _, _ = db.importuj_pytania("Quiz A", PYTANIA_TESTOWE.copy(), liczba_pytan=3)
    test_id_2, _, _ = db.importuj_pytania("Quiz B", PYTANIA_TESTOWE.copy(), liczba_pytan=3)

    (token_1,) = [w["token"] for w in db.wygeneruj_tokeny(test_id_1, 1, dlugosc=6)]
    (token_2,) = [w["token"] for w in db.wygeneruj_tokeny(test_id_2, 1, dlugosc=6)]

    przejdz_caly_test(klient, token_1)
    przejdz_caly_test(klient, token_2)

    strona_1 = klient.get(f"/admin/testy/{test_id_1}")
    assert token_1.encode() in strona_1.data
    assert token_2.encode() not in strona_1.data


# --- B20: brak wyników dla tokenu wraca do listy tokenów tego testu, nie do panelu -------

def test_szczegoly_niewykorzystanego_tokenu_wracaja_do_listy_tokenow(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    odpowiedz = klient.get(f"/admin/tokeny/{token}")
    assert odpowiedz.status_code == 302
    assert odpowiedz.headers["Location"] == f"/admin/testy/{test_z_pytaniami}/tokeny"


# --- B10: Post/Redirect/Get przy generowaniu tokenów — F5 nie pokazuje ich drugi raz -----

def test_odswiezenie_po_generowaniu_tokenow_nie_pokazuje_ich_ponownie(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    klient.post(
        f"/admin/testy/{test_z_pytaniami}/tokeny",
        data={"liczba": "3", "dlugosc": "6", "csrf_token": pobierz_csrf_token(klient)},
    )
    # Dwa kolejne GET-y symulują odświeżenie strony (F5) po przekierowaniu.
    pierwszy_get = klient.get(f"/admin/testy/{test_z_pytaniami}/tokeny")
    drugi_get = klient.get(f"/admin/testy/{test_z_pytaniami}/tokeny")

    assert b"Nowo wygenerowane tokeny" in pierwszy_get.data
    assert b"Nowo wygenerowane tokeny" not in drugi_get.data

    with db.baza() as conn:
        liczba = conn.execute(
            "SELECT COUNT(*) AS c FROM tokeny WHERE test_id = ?", (test_z_pytaniami,)
        ).fetchone()["c"]
    assert liczba == 3
