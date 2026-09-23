"""Testy Etapu 3 (patrz PLAN_POPRAWEK.md): import bez pandas przez openpyxl
(S1), walidacja wierszy z raportem błędów (B6), brak "nan"/"5.0" po pustych
komórkach (B5), ekran podglądu przed zatwierdzeniem i odrzucanie całego pliku
przy choćby jednym błędnym wierszu (L5), opcjonalna kolumna wyjaśnień (E4)."""

import db
from conftest import pobierz_csrf_token, zaloguj_admina
from pomocnicze import przejdz_caly_test, wyslij_import, wyslij_import_podglad


# --- B6: walidacja treści wiersz po wierszu, z czytelnym raportem błędów -----------------

def test_puste_pole_zglasza_blad_z_numerem_wiersza(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    wiersze = [
        {"tresc_pytania": "Q1", "opcja_a": "A", "opcja_b": "B", "opcja_c": "", "opcja_d": "D", "odpowiedz": "A"},
    ]
    odpowiedz = wyslij_import_podglad(klient, "Test z pustym polem", wiersze)
    assert "wiersz 2: puste pole".encode("utf-8") in odpowiedz.data
    assert b"opcja_c" in odpowiedz.data


def test_zla_litera_odpowiedzi_zglasza_blad(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    wiersze = [
        {"tresc_pytania": "Q1", "opcja_a": "A", "opcja_b": "B", "opcja_c": "C", "opcja_d": "D", "odpowiedz": "E"},
    ]
    odpowiedz = wyslij_import_podglad(klient, "Test ze zla litera", wiersze)
    assert "wiersz 2: nieprawidłowa odpowiedź".encode("utf-8") in odpowiedz.data
    assert "&#39;E&#39;".encode("utf-8") in odpowiedz.data


def test_naglowki_case_insensitive_i_ze_spacjami_importuja_sie_poprawnie(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    wiersze = [{"Tresc_Pytania": "Q1", " Opcja_A ": "A", "OPCJA_B": "B", "opcja_c": "C", "opcja_d": "D", "Odpowiedz": "b"}]
    kolumny = ["Tresc_Pytania", " Opcja_A ", "OPCJA_B", "opcja_c", "opcja_d", "Odpowiedz"]
    odpowiedz = wyslij_import(klient, "Test z naglowkami", wiersze, kolumny=kolumny)
    assert "Zaimportowano 1 pytań".encode("utf-8") in odpowiedz.data
    with db.baza() as conn:
        pytanie = conn.execute(
            "SELECT * FROM pytania WHERE test_id = (SELECT id FROM testy WHERE nazwa = 'Test z naglowkami')"
        ).fetchone()
    assert pytanie["odpowiedz"] == "B"


# --- L5: cały plik jest odrzucany, gdy choćby jeden wiersz ma błąd; podgląd przed zapisem -

def test_caly_plik_jest_odrzucany_gdy_jeden_wiersz_ma_blad(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    wiersze = [
        {"tresc_pytania": "Q1", "opcja_a": "A", "opcja_b": "B", "opcja_c": "C", "opcja_d": "D", "odpowiedz": "A"},
        {"tresc_pytania": "Q2", "opcja_a": "A", "opcja_b": "B", "opcja_c": "C", "opcja_d": "D", "odpowiedz": "E"},
    ]
    podglad = wyslij_import_podglad(klient, "Test mieszany", wiersze)
    assert "Wczytano 2 pytań, 1 z błędami".encode("utf-8") in podglad.data
    assert "Zatwierdź import".encode("utf-8") not in podglad.data

    with db.baza() as conn:
        test = conn.execute("SELECT 1 FROM testy WHERE nazwa = 'Test mieszany'").fetchone()
    assert test is None


def test_podglad_bez_bledow_pokazuje_przycisk_zatwierdzenia_i_nic_jeszcze_nie_zapisuje(klient, haslo_admina):
    from conftest import PYTANIA_TESTOWE

    zaloguj_admina(klient, haslo_admina)
    podglad = wyslij_import_podglad(klient, "Test podglad", PYTANIA_TESTOWE)
    assert "Wczytano 3 pytań bez błędów".encode("utf-8") in podglad.data
    assert "Zatwierdź import".encode("utf-8") in podglad.data

    with db.baza() as conn:
        test = conn.execute("SELECT 1 FROM testy WHERE nazwa = 'Test podglad'").fetchone()
    assert test is None


def test_zatwierdzenie_ze_spreparowanym_plikiem_z_bledami_jest_odrzucane(klient, haslo_admina):
    """Krok zatwierdzenia waliduje dane ponownie — spreparowane `plik_base64`
    wskazujące na plik z błędami (np. odpowiedź spoza A-D) nie zapisze się,
    nawet gdyby ktoś ominął ekran podglądu i wysłał POST bezpośrednio."""
    import base64

    from pomocnicze import zbuduj_xlsx

    zaloguj_admina(klient, haslo_admina)
    wiersze = [{"tresc_pytania": "Q1", "opcja_a": "A", "opcja_b": "B", "opcja_c": "C", "opcja_d": "D", "odpowiedz": "Z"}]
    plik_base64 = base64.b64encode(zbuduj_xlsx(wiersze).getvalue()).decode("ascii")

    odpowiedz = klient.post(
        "/admin/import/zatwierdz",
        data={
            "nazwa_testu": "Test spreparowany",
            "liczba_pytan": "20",
            "plik_base64": plik_base64,
            "csrf_token": pobierz_csrf_token(klient),
        },
        follow_redirects=True,
    )
    assert "błędy".encode("utf-8") in odpowiedz.data
    with db.baza() as conn:
        test = conn.execute("SELECT 1 FROM testy WHERE nazwa = 'Test spreparowany'").fetchone()
    assert test is None


# --- B5: puste komórki i liczby całkowite nie dają "nan" / "5.0" -------------------------

def test_komorka_na_tekst_usuwa_puste_wartosci_i_zbedna_kropke_zero():
    assert db._komorka_na_tekst(None) == ""
    assert db._komorka_na_tekst(5.0) == "5"
    assert db._komorka_na_tekst(5.5) == "5.5"
    assert db._komorka_na_tekst("  Warszawa  ") == "Warszawa"


def test_opcja_zapisana_jako_float_w_pliku_nie_zapisuje_sie_z_kropka_zero(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    wiersze = [
        {"tresc_pytania": "Ile to 2+3?", "opcja_a": 4, "opcja_b": 5.0, "opcja_c": 6, "opcja_d": 7, "odpowiedz": "B"},
    ]
    wyslij_import(klient, "Test liczby", wiersze)
    with db.baza() as conn:
        pytanie = conn.execute(
            "SELECT * FROM pytania WHERE test_id = (SELECT id FROM testy WHERE nazwa = 'Test liczby')"
        ).fetchone()
    assert pytanie["opcja_b"] == "5"
    assert "nan" not in pytanie["opcja_b"].lower()


# --- E4: opcjonalna kolumna wyjaśnienia --------------------------------------------------

def test_wyjasnienie_jest_opcjonalne_plik_bez_tej_kolumny_importuje_sie_normalnie(klient, haslo_admina):
    from conftest import PYTANIA_TESTOWE

    zaloguj_admina(klient, haslo_admina)
    odpowiedz = wyslij_import(klient, "Test bez wyjasnien", PYTANIA_TESTOWE)
    assert "Zaimportowano 3 pytań".encode("utf-8") in odpowiedz.data
    with db.baza() as conn:
        pytanie = conn.execute(
            "SELECT wyjasnienie FROM pytania WHERE test_id = (SELECT id FROM testy WHERE nazwa = 'Test bez wyjasnien') LIMIT 1"
        ).fetchone()
    assert pytanie["wyjasnienie"] is None


def test_wyjasnienie_jest_zapisywane_i_pokazywane_w_wyniku_uczestnika(klient):
    wiersze = [
        {
            "tresc_pytania": "Jaka jest stolica Francji?", "opcja_a": "Lyon", "opcja_b": "Paryż",
            "opcja_c": "Nicea", "opcja_d": "Marsylia", "odpowiedz": "B",
            "wyjasnienie": "Paryż jest stolicą Francji od średniowiecza.",
        },
    ]
    test_id, _, _ = db.importuj_pytania("Test z wyjasnieniem", wiersze, liczba_pytan=1)
    # Szczegóły są domyślnie widoczne dopiero po zamknięciu testu (F2) — ten test
    # sprawdza samą treść wyjaśnienia, więc włączamy widoczność „od razu”.
    db.zapisz_ustawienia_testu(test_id, None, "natychmiast", None, "od_razu", None, None)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_id, 1, dlugosc=6)]

    wynik = przejdz_caly_test(klient, token, litera_odpowiedzi="B")
    assert b"Poprawne odpowiedzi" in wynik.data

    sprawdzenie = klient.post("/sprawdz-wynik", data={"token": token}, follow_redirects=True)
    assert "Paryż jest stolicą Francji od średniowiecza.".encode("utf-8") in sprawdzenie.data


# --- S1: szablon do pobrania działa bez pandas i podpowiada kolumnę wyjaśnienia ----------

def test_szablon_zawiera_opcjonalna_kolumne_wyjasnienie(klient, haslo_admina):
    import io

    import openpyxl

    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.get("/admin/szablon-pytan.xlsx")
    skoroszyt = openpyxl.load_workbook(io.BytesIO(odpowiedz.data))
    naglowki = [str(h).strip().lower() for h in next(skoroszyt.active.iter_rows(values_only=True))]
    assert "wyjasnienie" in naglowki
