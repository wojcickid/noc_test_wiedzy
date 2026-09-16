"""Importuje pytania z pliku Excel do bazy SQLite jako nowy, nazwany test.

Każde uruchomienie tworzy nowy test (pytania różnych testów nie mieszają się) —
tokeny generowane przez generuj_tokeny.py wskazują, do którego testu dają dostęp.
To samo można zrobić przez panel administracyjny appki pod /admin/import.

Użycie:
    python importuj_pytania.py pytania.xlsx "Nazwa testu"
    python importuj_pytania.py pytania.xlsx "Nazwa testu" --liczba-pytan 10
"""

import argparse

import pandas as pd

from db import BladImportu, importuj_test_z_dataframe, inicjalizuj


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
    df = pd.read_excel(args.plik_xlsx)

    try:
        test_id, liczba, liczba_pytan = importuj_test_z_dataframe(args.nazwa_testu, df, args.liczba_pytan)
    except BladImportu as e:
        raise SystemExit(str(e))

    print(f"Zaimportowano {liczba} pytań jako test '{args.nazwa_testu}' (id={test_id}).")
    print(f"Losowanych na podejście: {liczba_pytan}.")
    print(f"Aby wygenerować tokeny dostępu: python generuj_tokeny.py \"{args.nazwa_testu}\" <liczba>")


if __name__ == "__main__":
    main()
