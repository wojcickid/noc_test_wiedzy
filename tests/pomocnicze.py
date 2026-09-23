"""Funkcje pomocnicze wspólne dla wielu plików testowych."""

import io
import re

import openpyxl


def przejdz_caly_test(klient, token, litera_odpowiedzi="B"):
    """Loguje się tokenem i odpowiada `litera_odpowiedzi` na każde pytanie,
    aż appka przekieruje na stronę wyniku. Zwraca ostatnią odpowiedź (stronę wyniku)."""
    odpowiedz = klient.post("/", data={"token": token}, follow_redirects=True)
    while True:
        dopasowanie = re.search(rb'name="pytanie_id" value="(\d+)"', odpowiedz.data)
        assert dopasowanie, f"Nie znaleziono pytania na stronie: {odpowiedz.data[:300]!r}"
        pytanie_id = dopasowanie.group(1).decode()
        odpowiedz = klient.post(
            "/test",
            data={"pytanie_id": pytanie_id, "odpowiedz": litera_odpowiedzi},
            follow_redirects=True,
        )
        if b"Poprawne odpowiedzi" in odpowiedz.data:
            return odpowiedz


def zbuduj_xlsx(wiersze, kolumny=None):
    """Buduje plik .xlsx w pamięci z listy słowników (albo z listy list, jeśli
    podano `kolumny` osobno) — zastępuje dawne budowanie testowych plików
    przez pandas (S1, Etap 3)."""
    if kolumny is None:
        kolumny = list(wiersze[0].keys()) if wiersze else []
    skoroszyt = openpyxl.Workbook()
    arkusz = skoroszyt.active
    arkusz.append(kolumny)
    for wiersz in wiersze:
        arkusz.append([wiersz.get(k) for k in kolumny])
    bufor = io.BytesIO()
    skoroszyt.save(bufor)
    bufor.seek(0)
    return bufor


def wyslij_import_podglad(klient, nazwa_testu, wiersze, liczba_pytan=20, kolumny=None):
    """Krok 1 importu (Etap 3, L5) — wysyła plik i zwraca stronę podglądu,
    bez zapisu do bazy."""
    from conftest import pobierz_csrf_token

    bufor = zbuduj_xlsx(wiersze, kolumny=kolumny)
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


def zatwierdz_import(klient, strona_podgladu):
    """Krok 2 importu — odczytuje ukryte pola z podglądu i zatwierdza zapis."""
    from conftest import pobierz_csrf_token

    plik_base64 = re.search(rb'name="plik_base64" value="([^"]*)"', strona_podgladu).group(1).decode()
    nazwa_testu = re.search(rb'name="nazwa_testu" value="([^"]*)"', strona_podgladu).group(1).decode()
    liczba_pytan = re.search(rb'name="liczba_pytan" value="([^"]*)"', strona_podgladu).group(1).decode()
    return klient.post(
        "/admin/import/zatwierdz",
        data={
            "nazwa_testu": nazwa_testu,
            "liczba_pytan": liczba_pytan,
            "plik_base64": plik_base64,
            "csrf_token": pobierz_csrf_token(klient),
        },
        follow_redirects=True,
    )


def wyslij_import(klient, nazwa_testu, wiersze, liczba_pytan=20, kolumny=None):
    """Pełny import (krok podglądu + zatwierdzenie), tak jak korzysta z niego
    uczestnik panelu. Zwraca odpowiedź po zatwierdzeniu."""
    podglad = wyslij_import_podglad(klient, nazwa_testu, wiersze, liczba_pytan, kolumny)
    return zatwierdz_import(klient, podglad.data)
