"""Testy Etapu 4 (patrz PLAN_POPRAWEK.md): limit czasu z licznikiem i tolerancją
(F1), widoczność wyniku/szczegółów, zamknięcie testu i okno dostępności (F2),
ekran startowy — zegar startuje dopiero po kliknięciu „Rozpoczynam” (E14)."""

import re
from datetime import datetime, timedelta

import db
from conftest import pobierz_csrf_token, zaloguj_admina


def _cofnij_start(token, sekundy_wstecz):
    """Przesuwa `data_rozpoczecia` podejścia w przeszłość o `sekundy_wstecz` —
    symuluje upływ czasu bez czekania w teście."""
    nowa_data = (datetime.now() - timedelta(seconds=sekundy_wstecz)).strftime(db.FORMAT_DATY)
    with db.baza() as conn:
        conn.execute("UPDATE podejscia SET data_rozpoczecia = ? WHERE token = ?", (nowa_data, token))


def _dokoncz_test(klient, token, litera_odpowiedzi="B"):
    """Jak `przejdz_caly_test`, ale nie zakłada, że wynik jest widoczny na
    stronie końcowej — zatrzymuje się, gdy na stronie nie ma już pytania."""
    odpowiedz = klient.post("/", data={"token": token}, follow_redirects=True)
    if b'name="start"' in odpowiedz.data:
        odpowiedz = klient.post("/test", data={"start": "1"}, follow_redirects=True)
    while True:
        dopasowanie = re.search(rb'name="pytanie_id" value="(\d+)"', odpowiedz.data)
        if not dopasowanie:
            return odpowiedz
        pytanie_id = dopasowanie.group(1).decode()
        odpowiedz = klient.post(
            "/test", data={"pytanie_id": pytanie_id, "odpowiedz": litera_odpowiedzi}, follow_redirects=True
        )


# --- E14: ekran startowy — zegar startuje dopiero po kliknięciu „Rozpoczynam” -----------

def test_wejscie_tokenem_nie_tworzy_jeszcze_podejscia(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)

    with db.baza() as conn:
        podejscie = conn.execute("SELECT 1 FROM podejscia WHERE token = ?", (token,)).fetchone()
    assert podejscie is None


def test_klikniecie_rozpoczynam_tworzy_podejscie_w_trakcie(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    klient.post("/test", data={"start": "1"}, follow_redirects=True)

    with db.baza() as conn:
        podejscie = conn.execute("SELECT status FROM podejscia WHERE token = ?", (token,)).fetchone()
    assert podejscie is not None
    assert podejscie["status"] == "w_trakcie"


# --- F1: limit czasu z licznikiem ---------------------------------------------------------

def test_licznik_pokazywany_gdy_test_ma_limit_czasu(klient, test_z_pytaniami):
    db.zapisz_ustawienia_testu(test_z_pytaniami, 10, "natychmiast", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    strona = klient.post("/test", data={"start": "1"}, follow_redirects=True)

    dopasowanie = re.search(rb'data-pozostalo-s="(\d+)"', strona.data)
    assert dopasowanie is not None
    pozostalo = int(dopasowanie.group(1))
    assert 590 <= pozostalo <= 600


def test_brak_licznika_gdy_test_bez_limitu_czasu(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    strona = klient.post("/test", data={"start": "1"}, follow_redirects=True)

    assert b'id="licznik"' not in strona.data


def test_podejscie_konczy_sie_automatycznie_po_uplywie_limitu_i_tolerancji(klient, test_z_pytaniami):
    db.zapisz_ustawienia_testu(test_z_pytaniami, 1, "natychmiast", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    klient.post("/test", data={"start": "1"}, follow_redirects=True)

    _cofnij_start(token, sekundy_wstecz=120)  # limit 1 min + 5 s tolerancji -> na pewno minęło

    strona = klient.get("/test", follow_redirects=True)
    assert "Czas na wypełnienie testu minął".encode("utf-8") in strona.data
    with db.baza() as conn:
        status = conn.execute("SELECT status FROM podejscia WHERE token = ?", (token,)).fetchone()["status"]
    assert status == "czas_minal"


def test_odpowiedz_zaakceptowana_w_granicach_tolerancji(klient, test_z_pytaniami):
    db.zapisz_ustawienia_testu(test_z_pytaniami, 1, "natychmiast", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    start = klient.post("/test", data={"start": "1"}, follow_redirects=True)
    pytanie_id = re.search(rb'name="pytanie_id" value="(\d+)"', start.data).group(1).decode()

    _cofnij_start(token, sekundy_wstecz=63)  # limit 60 s minęło, ale mieści się w 5 s tolerancji

    odpowiedz = klient.post("/test", data={"pytanie_id": pytanie_id, "odpowiedz": "B"}, follow_redirects=True)
    assert b"Pytanie 2 z 3" in odpowiedz.data
    with db.baza() as conn:
        liczba = conn.execute(
            "SELECT COUNT(*) AS c FROM odpowiedzi_uzytkownika WHERE token = ? AND pytanie_id = ?",
            (token, int(pytanie_id)),
        ).fetchone()["c"]
    assert liczba == 1


def test_odpowiedz_odrzucona_po_przekroczeniu_tolerancji(klient, test_z_pytaniami):
    db.zapisz_ustawienia_testu(test_z_pytaniami, 1, "natychmiast", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    start = klient.post("/test", data={"start": "1"}, follow_redirects=True)
    pytanie_id = re.search(rb'name="pytanie_id" value="(\d+)"', start.data).group(1).decode()

    _cofnij_start(token, sekundy_wstecz=70)  # limit 60 s + 5 s tolerancji przekroczone

    odpowiedz = klient.post("/test", data={"pytanie_id": pytanie_id, "odpowiedz": "B"}, follow_redirects=True)
    assert "Czas na wypełnienie testu minął".encode("utf-8") in odpowiedz.data
    with db.baza() as conn:
        liczba = conn.execute(
            "SELECT COUNT(*) AS c FROM odpowiedzi_uzytkownika WHERE token = ? AND pytanie_id = ?",
            (token, int(pytanie_id)),
        ).fetchone()["c"]
    assert liczba == 0


def test_auto_wyslany_formularz_bez_odpowiedzi_po_uplywie_limitu_konczy_test_od_razu(klient, test_z_pytaniami):
    """Licznik (F1) wysyła formularz automatycznie po upłynięciu limitu, nawet
    bez zaznaczonej odpowiedzi. To nie powinno wracać do "Zaznacz odpowiedź"
    (co dawało pętlę GET/POST aż do końca 5 s tolerancji) — test ma się
    zakończyć od razu, w granicach nominalnego limitu, bez czekania na
    tolerancję."""
    db.zapisz_ustawienia_testu(test_z_pytaniami, 1, "natychmiast", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    start = klient.post("/test", data={"start": "1"}, follow_redirects=True)
    pytanie_id = re.search(rb'name="pytanie_id" value="(\d+)"', start.data).group(1).decode()

    _cofnij_start(token, sekundy_wstecz=61)  # limit 60 s minęło, ale wciąż w 5 s tolerancji

    odpowiedz = klient.post("/test", data={"pytanie_id": pytanie_id}, follow_redirects=True)
    assert "Czas na wypełnienie testu minął".encode("utf-8") in odpowiedz.data
    assert "Zaznacz odpowiedź, aby przejść dalej.".encode("utf-8") not in odpowiedz.data
    with db.baza() as conn:
        status = conn.execute("SELECT status FROM podejscia WHERE token = ?", (token,)).fetchone()["status"]
    assert status == "czas_minal"


def test_zmiana_limitu_na_zywo_wplywa_na_trwajace_podejscie(klient, test_z_pytaniami):
    """Ustawienia zapisane przez admina są czytane na żywo przy każdym wejściu
    na /test — skrócenie limitu w trakcie podejścia od razu wpływa na nie
    (decyzja usera z Etapu 4: limit czasu musi być opcjonalny i konfigurowalny)."""
    db.zapisz_ustawienia_testu(test_z_pytaniami, 10, "natychmiast", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    klient.post("/test", data={"start": "1"}, follow_redirects=True)

    _cofnij_start(token, sekundy_wstecz=300)  # 5 minut temu — wciąż w limicie 10 minut
    przed = klient.get("/test", follow_redirects=True)
    assert b"Pytanie 1 z 3" in przed.data

    db.zapisz_ustawienia_testu(test_z_pytaniami, 1, "natychmiast", None, "od_razu", None, None)
    po = klient.get("/test", follow_redirects=True)
    assert "Czas na wypełnienie testu minął".encode("utf-8") in po.data


# --- F2: widoczność wyniku i szczegółów ---------------------------------------------------

def test_wynik_widoczny_od_razu_mimo_domyslnie_ukrytych_szczegolow(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    odpowiedz = _dokoncz_test(klient, token, "B")
    assert b"Poprawne odpowiedzi: 3 / 3" in odpowiedz.data


def test_szczegoly_tryb_natychmiast_widoczne_od_razu(klient, test_z_pytaniami):
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "natychmiast", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    _dokoncz_test(klient, token, "B")

    odpowiedz = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert odpowiedz.data.count(b'<tr class="ok"') == 3


def test_szczegoly_tryb_po_zamknieciu_ukryte_dopoki_test_otwarty(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    _dokoncz_test(klient, token, "B")

    odpowiedz = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert b'<tr class="ok"' not in odpowiedz.data
    assert "Szczegółowe odpowiedzi będą dostępne po zakończeniu testu przez prowadzącego.".encode(
        "utf-8"
    ) in odpowiedz.data


def test_szczegoly_tryb_po_zamknieciu_widoczne_po_zamknieciu_testu(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    _dokoncz_test(klient, token, "B")
    db.ustaw_zamkniecie_testu(test_z_pytaniami, True)

    odpowiedz = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert odpowiedz.data.count(b'<tr class="ok"') == 3


def test_szczegoly_tryb_od_daty_ukryte_przed_data_widoczne_po(klient, test_z_pytaniami):
    przyszlosc = (datetime.now() + timedelta(hours=1)).strftime(db.FORMAT_DATY)
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "od_daty", przyszlosc, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    _dokoncz_test(klient, token, "B")

    odpowiedz = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert b'<tr class="ok"' not in odpowiedz.data

    przeszlosc = (datetime.now() - timedelta(hours=1)).strftime(db.FORMAT_DATY)
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "od_daty", przeszlosc, "od_razu", None, None)
    odpowiedz2 = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert odpowiedz2.data.count(b'<tr class="ok"') == 3


def test_szczegoly_tryb_nigdy_zawsze_ukryte_nawet_po_zamknieciu(klient, test_z_pytaniami):
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "nigdy", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    _dokoncz_test(klient, token, "B")
    db.ustaw_zamkniecie_testu(test_z_pytaniami, True)

    odpowiedz = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert b'<tr class="ok"' not in odpowiedz.data
    assert "Szczegółowe odpowiedzi są dostępne tylko dla prowadzącego.".encode("utf-8") in odpowiedz.data


def test_wynik_razem_ze_szczegolami_ukrywa_tez_wynik_punktowy_do_zamkniecia(klient, test_z_pytaniami):
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "po_zamknieciu", None, "razem_ze_szczegolami", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    _dokoncz_test(klient, token, "B")

    odpowiedz = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert b"Wynik:" not in odpowiedz.data

    db.ustaw_zamkniecie_testu(test_z_pytaniami, True)
    odpowiedz2 = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert b"Wynik: 3 / 3" in odpowiedz2.data


def test_wynik_strona_ukrywa_wynik_gdy_tryb_wymaga_zamkniecia(klient, test_z_pytaniami):
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "po_zamknieciu", None, "razem_ze_szczegolami", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    odpowiedz = _dokoncz_test(klient, token, "B")
    assert b"Poprawne odpowiedzi: 3 / 3" not in odpowiedz.data
    assert "Wynik będzie można sprawdzić później".encode("utf-8") in odpowiedz.data


# --- F2: zamknięcie testu i okno dostępności ----------------------------------------------

def test_zamkniecie_testu_blokuje_nowe_podejscie(klient, test_z_pytaniami):
    db.ustaw_zamkniecie_testu(test_z_pytaniami, True)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    odpowiedz = klient.post("/", data={"token": token}, follow_redirects=True)
    assert "Ten test został zamknięty przez prowadzącego.".encode("utf-8") in odpowiedz.data


def test_zamkniecie_testu_nie_blokuje_wznowienia_trwajacego_podejscia(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    klient.post("/test", data={"start": "1"}, follow_redirects=True)

    db.ustaw_zamkniecie_testu(test_z_pytaniami, True)
    wznowienie = klient.post("/", data={"token": token}, follow_redirects=True)
    assert b"Pytanie 1 z 3" in wznowienie.data


def test_dostepny_od_w_przyszlosci_blokuje_nowe_podejscie(klient, test_z_pytaniami):
    przyszlosc = (datetime.now() + timedelta(hours=1)).strftime(db.FORMAT_DATY)
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "natychmiast", None, "od_razu", przyszlosc, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    odpowiedz = klient.post("/", data={"token": token}, follow_redirects=True)
    assert "Ten test będzie dostępny od".encode("utf-8") in odpowiedz.data


def test_dostepny_do_w_przeszlosci_blokuje_nowe_podejscie(klient, test_z_pytaniami):
    przeszlosc = (datetime.now() - timedelta(hours=1)).strftime(db.FORMAT_DATY)
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "natychmiast", None, "od_razu", None, przeszlosc)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    odpowiedz = klient.post("/", data={"token": token}, follow_redirects=True)
    assert "Termin na rozpoczęcie tego testu już minął.".encode("utf-8") in odpowiedz.data


def test_start_w_oknie_dostepnosci_jest_dozwolony(klient, test_z_pytaniami):
    od = (datetime.now() - timedelta(hours=1)).strftime(db.FORMAT_DATY)
    do = (datetime.now() + timedelta(hours=1)).strftime(db.FORMAT_DATY)
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "natychmiast", None, "od_razu", od, do)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    odpowiedz = klient.post("/", data={"token": token}, follow_redirects=True)
    assert b"Rozpoczynam" in odpowiedz.data


def test_okno_dostepnosci_nie_blokuje_wznowienia_trwajacego_podejscia(klient, test_z_pytaniami):
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    klient.post("/test", data={"start": "1"}, follow_redirects=True)

    przeszlosc = (datetime.now() - timedelta(minutes=1)).strftime(db.FORMAT_DATY)
    db.zapisz_ustawienia_testu(test_z_pytaniami, None, "natychmiast", None, "od_razu", None, przeszlosc)

    wznowienie = klient.post("/", data={"token": token}, follow_redirects=True)
    assert b"Pytanie 1 z 3" in wznowienie.data


# --- Panel administracyjny: ustawienia testu (Etap 4) --------------------------------------

def test_admin_ustawienia_wymaga_logowania(klient, test_z_pytaniami):
    odpowiedz = klient.get(f"/admin/testy/{test_z_pytaniami}/ustawienia")
    assert odpowiedz.status_code == 302
    assert "/admin/login" in odpowiedz.headers["Location"]


def test_admin_ustawienia_wymaga_csrf(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post(f"/admin/testy/{test_z_pytaniami}/ustawienia", data={"limit_czasu_min": "5"})
    assert odpowiedz.status_code == 400


def test_admin_zapisuje_poprawne_ustawienia(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post(
        f"/admin/testy/{test_z_pytaniami}/ustawienia",
        data={
            "csrf_token": pobierz_csrf_token(klient),
            "limit_czasu_min": "15",
            "wynik_widoczny": "od_razu",
            "tryb_szczegolow": "natychmiast",
            "szczegoly_od": "",
            "dostepny_od": "",
            "dostepny_do": "",
        },
        follow_redirects=True,
    )
    assert "Zapisano ustawienia testu.".encode("utf-8") in odpowiedz.data
    with db.baza() as conn:
        test = conn.execute("SELECT * FROM testy WHERE id = ?", (test_z_pytaniami,)).fetchone()
    assert test["limit_czasu_min"] == 15
    assert test["tryb_szczegolow"] == "natychmiast"


def test_admin_zmienia_liczbe_losowanych_pytan_po_imporcie(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post(
        f"/admin/testy/{test_z_pytaniami}/ustawienia",
        data={
            "csrf_token": pobierz_csrf_token(klient),
            "liczba_pytan_do_losowania": "2",
            "limit_czasu_min": "",
            "wynik_widoczny": "od_razu",
            "tryb_szczegolow": "natychmiast",
        },
        follow_redirects=True,
    )
    assert "Zapisano ustawienia testu.".encode("utf-8") in odpowiedz.data
    with db.baza() as conn:
        test = conn.execute("SELECT liczba_pytan_do_losowania FROM testy WHERE id = ?", (test_z_pytaniami,)).fetchone()
    assert test["liczba_pytan_do_losowania"] == 2

    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    strona = klient.post("/test", data={"start": "1"}, follow_redirects=True)
    assert b"Pytanie 1 z 2" in strona.data


def test_admin_liczba_losowanych_pytan_ograniczona_do_rozmiaru_banku(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post(
        f"/admin/testy/{test_z_pytaniami}/ustawienia",
        data={
            "csrf_token": pobierz_csrf_token(klient),
            "liczba_pytan_do_losowania": "999",
            "limit_czasu_min": "",
            "wynik_widoczny": "od_razu",
            "tryb_szczegolow": "natychmiast",
        },
        follow_redirects=True,
    )
    assert "w banku jest tylko 3 pytań".encode("utf-8") in odpowiedz.data
    with db.baza() as conn:
        test = conn.execute("SELECT liczba_pytan_do_losowania FROM testy WHERE id = ?", (test_z_pytaniami,)).fetchone()
    assert test["liczba_pytan_do_losowania"] == 3


def test_admin_odrzuca_nieprawidlowy_tryb_szczegolow(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post(
        f"/admin/testy/{test_z_pytaniami}/ustawienia",
        data={
            "csrf_token": pobierz_csrf_token(klient),
            "limit_czasu_min": "",
            "wynik_widoczny": "od_razu",
            "tryb_szczegolow": "cos_dziwnego",
        },
        follow_redirects=True,
    )
    assert "Nieprawidłowe ustawienia widoczności.".encode("utf-8") in odpowiedz.data


def test_admin_odrzuca_ujemny_limit_czasu(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post(
        f"/admin/testy/{test_z_pytaniami}/ustawienia",
        data={
            "csrf_token": pobierz_csrf_token(klient),
            "limit_czasu_min": "-5",
            "wynik_widoczny": "od_razu",
            "tryb_szczegolow": "natychmiast",
        },
        follow_redirects=True,
    )
    assert "Limit czasu musi być dodatnią liczbą minut".encode("utf-8") in odpowiedz.data


def test_admin_zapisuje_okno_dostepnosci_z_formularza_i_wstepnie_je_wypelnia(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    klient.post(
        f"/admin/testy/{test_z_pytaniami}/ustawienia",
        data={
            "csrf_token": pobierz_csrf_token(klient),
            "limit_czasu_min": "",
            "wynik_widoczny": "od_razu",
            "tryb_szczegolow": "natychmiast",
            "dostepny_od": "2026-01-01T10:00",
            "dostepny_do": "2026-12-31T23:59",
        },
        follow_redirects=True,
    )
    with db.baza() as conn:
        test = conn.execute(
            "SELECT dostepny_od, dostepny_do FROM testy WHERE id = ?", (test_z_pytaniami,)
        ).fetchone()
    assert test["dostepny_od"] == "2026-01-01 10:00:00"
    assert test["dostepny_do"] == "2026-12-31 23:59:00"

    strona = klient.get(f"/admin/testy/{test_z_pytaniami}/ustawienia")
    assert b'value="2026-01-01T10:00"' in strona.data


def test_admin_widok_testu_pokazuje_znacznik_zamkniety(klient, haslo_admina, test_z_pytaniami):
    db.ustaw_zamkniecie_testu(test_z_pytaniami, True)
    zaloguj_admina(klient, haslo_admina)

    strona = klient.get(f"/admin/testy/{test_z_pytaniami}")
    assert b"badge-zamkniety" in strona.data
    assert "Zamknięty".encode("utf-8") in strona.data


def test_admin_widok_tokenow_pokazuje_czas_minal_po_wygasnieciu(klient, haslo_admina, test_z_pytaniami):
    db.zapisz_ustawienia_testu(test_z_pytaniami, 1, "natychmiast", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]
    klient.post("/", data={"token": token}, follow_redirects=True)
    klient.post("/test", data={"start": "1"}, follow_redirects=True)
    _cofnij_start(token, sekundy_wstecz=300)

    zaloguj_admina(klient, haslo_admina)
    strona = klient.get(f"/admin/testy/{test_z_pytaniami}/tokeny")
    assert "czas minął".encode("utf-8") in strona.data
    with db.baza() as conn:
        status = conn.execute("SELECT status FROM podejscia WHERE token = ?", (token,)).fetchone()["status"]
    assert status == "czas_minal"
