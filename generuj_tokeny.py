"""Generuje jednorazowe tokeny dostępu do wskazanego testu (zapisane w bazie SQLite).
To samo można zrobić przez panel administracyjny appki pod /admin/testy/<id>/tokeny.

Użycie:
    python generuj_tokeny.py "Nazwa testu" 50
    python generuj_tokeny.py "Nazwa testu" 50 --dlugosc 6
    python generuj_tokeny.py "Nazwa testu" --lista uczestnicy.txt
        (plik tekstowy, jedna osoba na linię: "Imię Nazwisko;e-mail", samo imię
        albo sam e-mail; każda linia dostaje własny, przypisany token)
    python generuj_tokeny.py "Nazwa testu" --lista uczestnicy.xlsx
        (albo .csv — w pierwszym wierszu nagłówki kolumn "imie" i/lub "email")
"""

import argparse

from db import baza, inicjalizuj, opis_uczestnika, parsuj_liste_uczestnikow, wczytaj_plik_uczestnikow, wygeneruj_tokeny


def main():
    parser = argparse.ArgumentParser(description="Generuje jednorazowe tokeny dostępu do testu.")
    parser.add_argument("nazwa_testu", help="Nazwa testu (z importu pytań), do którego mają dawać dostęp tokeny")
    parser.add_argument("liczba", type=int, nargs="?", help="Ile nowych, anonimowych tokenów wygenerować")
    parser.add_argument("--dlugosc", type=int, default=8, help="Długość tokenu (domyślnie 8)")
    parser.add_argument("--lista", help="Plik tekstowy z listą uczestników (jedna osoba na linię) zamiast --liczba")
    args = parser.parse_args()

    if not args.lista and args.liczba is None:
        raise SystemExit("Podaj liczbę tokenów albo --lista pliku z uczestnikami.")

    inicjalizuj()

    with baza() as conn:
        wiersz = conn.execute("SELECT id FROM testy WHERE nazwa = ?", (args.nazwa_testu,)).fetchone()
        if wiersz is None:
            dostepne = conn.execute("SELECT nazwa FROM testy ORDER BY nazwa").fetchall()
            lista_testow = ", ".join(w["nazwa"] for w in dostepne) or "(brak zaimportowanych testów — użyj najpierw importuj_pytania.py)"
            raise SystemExit(f"Nie znaleziono testu '{args.nazwa_testu}'. Dostępne testy: {lista_testow}")
        test_id = wiersz["id"]

    try:
        if args.lista:
            if args.lista.lower().endswith((".xlsx", ".csv")):
                with open(args.lista, "rb") as f:
                    uczestnicy, bledy = wczytaj_plik_uczestnikow(f.read(), args.lista)
            else:
                with open(args.lista, "r", encoding="utf-8-sig") as f:
                    uczestnicy, bledy = parsuj_liste_uczestnikow(f.read())
            if bledy:
                raise SystemExit(f"Błędy w pliku '{args.lista}' — nic nie wygenerowano:\n" + "\n".join(bledy))
            if not uczestnicy:
                raise SystemExit(f"Plik '{args.lista}' nie zawiera żadnych uczestników.")
            nowe = wygeneruj_tokeny(test_id, len(uczestnicy), args.dlugosc, uczestnicy=uczestnicy)
        else:
            nowe = wygeneruj_tokeny(test_id, args.liczba, args.dlugosc)
    except ValueError as e:
        raise SystemExit(str(e))

    print(f"Wygenerowano {len(nowe)} nowych tokenów dla testu '{args.nazwa_testu}'.")
    print("Nowe tokeny:")
    for wpis in nowe:
        opis = opis_uczestnika(wpis["imie"], wpis["email"])
        if opis:
            print(f"{wpis['token']}  —  {opis}")
        else:
            print(wpis["token"])


if __name__ == "__main__":
    main()
