"""Importuje pytania z pliku Excel do bazy SQLite jako nowy, nazwany test.

Każde uruchomienie tworzy nowy test (pytania różnych testów nie mieszają się) —
tokeny generowane przez generuj_tokeny.py wskazują, do którego testu dają dostęp.
To samo można zrobić przez panel administracyjny appki pod /admin/import.

Użycie:
    python importuj_pytania.py pytania.xlsx "Nazwa testu"
    python importuj_pytania.py pytania.xlsx "Nazwa testu" --liczba-pytan 10
"""

import argparse

from db import BladImportu, importuj_pytania, inicjalizuj, wczytaj_i_zwaliduj_plik_pytan


def main():
    parser = argparse.ArgumentParser(description="Importuje pytania z Excela jako nowy test.")
    parser.add_argument("plik_xlsx", help="Ścieżka do pliku .xlsx z pytaniami")
    parser.add_argument("nazwa_testu", help="Nazwa nowego testu (musi być unikalna)")
    parser.add_argument(
        "--liczba-pytan", type=int, default=20, dest="liczba_pytan",
        help="Ile pytań losować przy każdym podejściu (domyślnie 20, przycinane do liczby pytań w pliku)",
    )
    args = parser.parse_args()

    inicjalizuj()
    try:
        with open(args.plik_xlsx, "rb") as f:
            dane_pliku = f.read()
    except OSError as e:
        raise SystemExit(f"Nie udało się odczytać pliku '{args.plik_xlsx}': {e}")

    pytania, bledy = wczytaj_i_zwaliduj_plik_pytan(dane_pliku)
    if bledy:
        print(f"Plik zawiera błędy ({len(bledy)}) — popraw je i spróbuj ponownie:")
        for blad in bledy:
            print(f"  - {blad}")
        raise SystemExit(1)

    try:
        test_id, liczba, liczba_pytan = importuj_pytania(args.nazwa_testu, pytania, args.liczba_pytan)
    except BladImportu as e:
        raise SystemExit(str(e))

    print(f"Zaimportowano {liczba} pytań jako test '{args.nazwa_testu}' (id={test_id}).")
    print(f"Losowanych na podejście: {liczba_pytan}.")
    print(f"Aby wygenerować tokeny dostępu: python generuj_tokeny.py \"{args.nazwa_testu}\" <liczba>")


if __name__ == "__main__":
    main()
