"""Testy obecnego przepływu uczestnika: token -> pytania -> wynik -> sprawdzenie wyniku.

Siatka bezpieczeństwa (S4, Etap 0) przed przebudową przebiegu testu w Etapie 2.
"""

import db
from pomocnicze import przejdz_caly_test


def test_zly_token_pokazuje_blad_i_nie_wpuszcza_do_testu(klient, test_z_pytaniami):
    odpowiedz = klient.post("/", data={"token": "NIEISTNIEJACY"}, follow_redirects=True)
    assert "Nieprawidłowy token dostępu.".encode("utf-8") in odpowiedz.data
    assert b"Pytanie 1 z" not in odpowiedz.data


def test_pusty_token_pokazuje_blad(klient, test_z_pytaniami):
    odpowiedz = klient.post("/", data={"token": ""}, follow_redirects=True)
    assert "Podaj token dostępu.".encode("utf-8") in odpowiedz.data


def test_start_testu_pokazuje_ekran_startowy(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    start = klient.post("/", data={"token": token}, follow_redirects=True)
    assert b"Rozpoczynam" in start.data

    pytanie = klient.post("/test", data={"start": "1"}, follow_redirects=True)
    assert b"Pytanie 1 z 3" in pytanie.data


def test_pelny_przeplyw_od_startu_do_wyniku(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    wynik = przejdz_caly_test(klient, token, litera_odpowiedzi="B")
    assert b"Poprawne odpowiedzi: 3 / 3" in wynik.data


def test_czesciowo_bledne_odpowiedzi_licza_sie_poprawnie(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    # "A" jest zawsze błędną odpowiedzią w PYTANIA_TESTOWE (poprawna to zawsze "B")
    wynik = przejdz_caly_test(klient, token, litera_odpowiedzi="A")
    assert b"Poprawne odpowiedzi: 0 / 3" in wynik.data


def test_powtorne_uzycie_tokenu_jest_zablokowane(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    przejdz_caly_test(klient, token)

    ponownie = klient.post("/", data={"token": token}, follow_redirects=True)
    assert "Ten token został już wykorzystany.".encode("utf-8") in ponownie.data


def test_brak_zaznaczonej_odpowiedzi_nie_przechodzi_dalej(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    start = klient.post("/test", data={"start": "1"}, follow_redirects=True)

    import re

    pytanie_id = re.search(rb'name="pytanie_id" value="(\d+)"', start.data).group(1).decode()
    odpowiedz = klient.post("/test", data={"pytanie_id": pytanie_id}, follow_redirects=True)

    assert "Zaznacz odpowiedź, aby przejść dalej.".encode("utf-8") in odpowiedz.data
    assert b"Pytanie 1 z 3" in odpowiedz.data


def test_sprawdz_wynik_pokazuje_szczegoly_po_ukonczeniu(klient, test_z_pytaniami):
    # Szczegóły są domyślnie widoczne dopiero po zamknięciu testu (F2) — ten test
    # sprawdza samą tabelę szczegółów, więc włączamy widoczność „od razu”.
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "natychmiast", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    przejdz_caly_test(klient, token, litera_odpowiedzi="B")

    odpowiedz = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert b"Wynik: 3 / 3" in odpowiedz.data
    assert odpowiedz.data.count(b'<tr class="ok"') == 3


def test_sprawdz_wynik_nieznany_token_pokazuje_komunikat(klient, test_z_pytaniami):
    odpowiedz = klient.post("/sprawdz-wynik", data={"token": "COSTAMBADZO"}, follow_redirects=True)
    assert "Nie znaleziono wyników dla podanego tokenu".encode("utf-8") in odpowiedz.data
