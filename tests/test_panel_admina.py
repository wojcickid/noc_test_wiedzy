"""Testy panelu administracyjnego: logowanie, kontrola dostępu, import, tokeny."""

import io

import db
from conftest import pobierz_csrf_token, zaloguj_admina


def test_logowanie_zlym_haslem_pokazuje_blad(klient):
    odpowiedz = klient.post("/admin/login", data={"haslo": "na-pewno-zle"}, follow_redirects=True)
    assert "Nieprawidłowe hasło.".encode("utf-8") in odpowiedz.data


def test_logowanie_dobrym_haslem_daje_dostep_do_panelu(klient, haslo_admina):
    odpowiedz = zaloguj_admina(klient, haslo_admina)
    assert "Brak zaimportowanych testów.".encode("utf-8") in odpowiedz.data


def test_dostep_do_panelu_bez_logowania_przekierowuje_na_login(klient):
    odpowiedz = klient.get("/admin", follow_redirects=True)
    assert "Hasło administratora:".encode("utf-8") in odpowiedz.data


def test_wylogowanie_odbiera_dostep(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    klient.post("/admin/logout", data={"csrf_token": pobierz_csrf_token(klient)})
    odpowiedz = klient.get("/admin", follow_redirects=True)
    assert "Hasło administratora:".encode("utf-8") in odpowiedz.data


def _wyslij_import(klient, nazwa_testu, df, liczba_pytan=20):
    bufor = io.BytesIO()
    df.to_excel(bufor, index=False)
    bufor.seek(0)
    return klient.post(
        "/admin/import",
        data={
            "nazwa_testu": nazwa_testu,
            "plik": (bufor, "pytania.xlsx"),
            "liczba_pytan": str(liczba_pytan),
            "csrf_token": pobierz_csrf_token(klient),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_import_pustej_nazwy_testu_pokazuje_blad(klient, haslo_admina):
    from conftest import PYTANIA_TESTOWE

    zaloguj_admina(klient, haslo_admina)
    odpowiedz = _wyslij_import(klient, "", PYTANIA_TESTOWE)
    assert "Podaj nazwę testu.".encode("utf-8") in odpowiedz.data


def test_import_duplikatu_nazwy_pokazuje_blad(klient, haslo_admina):
    from conftest import PYTANIA_TESTOWE

    zaloguj_admina(klient, haslo_admina)
    _wyslij_import(klient, "Test A", PYTANIA_TESTOWE)
    odpowiedz = _wyslij_import(klient, "Test A", PYTANIA_TESTOWE)
    assert "już istnieje".encode("utf-8") in odpowiedz.data


def test_import_pliku_z_brakujacymi_kolumnami_pokazuje_blad(klient, haslo_admina):
    import pandas as pd

    zaloguj_admina(klient, haslo_admina)
    zly_df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    odpowiedz = _wyslij_import(klient, "Zly test", zly_df)
    assert "brakuje kolumn".encode("utf-8") in odpowiedz.data


def test_import_przycina_liczbe_pytan_do_dostepnej_w_pliku(klient, haslo_admina):
    from conftest import PYTANIA_TESTOWE

    zaloguj_admina(klient, haslo_admina)
    # PYTANIA_TESTOWE ma 3 wiersze, prosimy o 20
    odpowiedz = _wyslij_import(klient, "Test przyciety", PYTANIA_TESTOWE, liczba_pytan=20)
    assert "Uwaga: plik ma tylko".encode("utf-8") in odpowiedz.data
    assert b"losowanie: 3 na podej" in odpowiedz.data


def test_przyklad_dziala_i_nadaje_unikalne_nazwy_przy_powtorzeniach(klient, haslo_admina):
    zaloguj_admina(klient, haslo_admina)
    csrf = pobierz_csrf_token(klient)
    pierwszy = klient.post("/admin/import/przyklad", data={"csrf_token": csrf}, follow_redirects=True)
    assert "Przykładowy test".encode("utf-8") in pierwszy.data

    drugi = klient.post("/admin/import/przyklad", data={"csrf_token": csrf}, follow_redirects=True)
    assert "Przykładowy test 2".encode("utf-8") in drugi.data


def test_szablon_do_pobrania_ma_wlasciwe_kolumny(klient, haslo_admina):
    import pandas as pd

    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.get("/admin/szablon-pytan.xlsx")
    assert odpowiedz.status_code == 200
    df = pd.read_excel(io.BytesIO(odpowiedz.data))
    oczekiwane = {"tresc_pytania", "opcja_a", "opcja_b", "opcja_c", "opcja_d", "odpowiedz"}
    assert oczekiwane.issubset(set(df.columns))


def test_generowanie_tokenow_anonimowych(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post(
        f"/admin/testy/{test_z_pytaniami}/tokeny",
        data={"liczba": "5", "dlugosc": "6", "csrf_token": pobierz_csrf_token(klient)},
        follow_redirects=True,
    )
    assert b"Wygenerowano 5 nowych token" in odpowiedz.data


def test_generowanie_tokenow_z_lista_uczestnikow_przypisuje_osoby(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    odpowiedz = klient.post(
        f"/admin/testy/{test_z_pytaniami}/tokeny",
        data={"lista_uczestnikow": "Jan Kowalski\nAnna Nowak", "dlugosc": "6", "csrf_token": pobierz_csrf_token(klient)},
        follow_redirects=True,
    )
    assert "Jan Kowalski".encode("utf-8") in odpowiedz.data
    assert "Anna Nowak".encode("utf-8") in odpowiedz.data


def test_przypisanie_tokenu_mozna_zmienic(klient, haslo_admina, test_z_pytaniami):
    zaloguj_admina(klient, haslo_admina)
    (token,) = [w["token"] for w in db.wygeneruj_tokeny(test_z_pytaniami, 1, dlugosc=6)]

    odpowiedz = klient.post(
        f"/admin/tokeny/{token}/przypisz",
        data={"przypisany": "Nowa Osoba", "test_id": str(test_z_pytaniami), "csrf_token": pobierz_csrf_token(klient)},
        follow_redirects=True,
    )
    assert "Zapisano przypisanie".encode("utf-8") in odpowiedz.data
    assert "Nowa Osoba".encode("utf-8") in odpowiedz.data
