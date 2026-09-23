# Test wiedzy — Nocowanie.pl

> Wyłącznie do użytku wewnętrznego w firmie — nie jest to narzędzie publiczne.

Aplikacja Flask do przeprowadzania quizów wiedzy: uczestnicy logują się jednorazowym
tokenem (bez podawania danych osobowych), odpowiadają na losowy zestaw pytań pokazywanych
pojedynczo, a admin zarządza wszystkim przez wbudowany panel administracyjny.

## Funkcje

- Logowanie jednorazowym tokenem zamiast e-maila — token jest zużywany od razu przy starcie testu.
- Pytania wyświetlane pojedynczo, z sekwencyjnym przechodzeniem dalej.
- Wiele niezależnych testów (różnych banków pytań) w jednej instalacji, każdy z własną
  liczbą losowanych pytań, ustawianą przy imporcie.
- Panel administracyjny (`/admin`, chroniony hasłem) do importu pytań, generowania
  tokenów (pojedynczo lub z listy uczestników z przypisanym imieniem/mailem) oraz
  podglądu wyników zbiorczych i szczegółowych.
- Eksport wyników do Excela (arkusz zbiorczy i szczegółowy), eksport tokenów do CSV
  i kopiowanie ich do schowka, statystyki pytań (% poprawnych, rozkład A–D).
- Próg zaliczenia per test (domyślnie 80%, można zmienić albo wyłączyć) — informacja
  zdał/nie zdał w wynikach admina i dla uczestnika.
- Uczestnik może samodzielnie sprawdzić swój wynik po tokenie (`/sprawdz-wynik`).
- Dane (testy, pytania, tokeny, odpowiedzi) w lokalnej bazie SQLite.

## Wymagania

- Python 3.10+
- Windows (skrypty `.bat`) — kod jest zwykłym Flaskiem, więc uruchomi się też na innych
  systemach ręcznie przez `python test_wiedzy_app.py`, ale gotowe skrypty startowe są
  pod Windows.

## Szybki start

1. Uruchom [`web_app.bat`](web_app.bat) — przy pierwszym starcie utworzy `.venv`,
   zainstaluje zależności z [`requirements.txt`](requirements.txt) i wystartuje appkę na
   `http://localhost:5555`.
2. Wejdź na `http://localhost:5555/admin`. Hasło administratora generuje się
   automatycznie przy pierwszym starcie — zobaczysz je w konsoli i w pliku
   `.admin_haslo` (nieśledzonym w git). Żeby zmienić hasło, edytuj ten plik
   i zrestartuj aplikację — hasło jest wczytywane tylko raz, przy starcie.
3. W panelu zaimportuj pytania (plik `.xlsx` albo przycisk „Wgraj przykładowy test”)
   i wygeneruj tokeny dla testu.
4. Rozdaj tokeny uczestnikom — wchodzą na stronę główną i wpisują swój kod.

## Uruchomienie produkcyjne

Wbudowany serwer deweloperski Flaska nie nadaje się do obsługi wielu uczestników naraz.
Do realnego wydarzenia użyj [`web_app_produkcja.bat`](web_app_produkcja.bat) — startuje
appkę przez serwer WSGI [Waitress](https://docs.pylonsproject.org/projects/waitress/)
zamiast wbudowanego dev-servera.

## Format pliku z pytaniami (.xlsx)

Wymagane kolumny: `tresc_pytania`, `opcja_a`, `opcja_b`, `opcja_c`, `opcja_d`,
`odpowiedz` (litera `A`/`B`/`C`/`D`). Szablon do pobrania w panelu administracyjnym
pod adresem `/admin/szablon-pytan.xlsx` (link na stronie `/admin/import`).

## Skrypty CLI

To samo, co w panelu administracyjnym, da się zrobić też z linii poleceń:

```
python importuj_pytania.py pytania.xlsx "Nazwa testu" [--liczba-pytan 20]
python generuj_tokeny.py "Nazwa testu" 50 [--dlugosc 8]
python generuj_tokeny.py "Nazwa testu" --lista uczestnicy.txt
```

`uczestnicy.txt` to zwykły plik tekstowy, jedna osoba (imię i/lub e-mail) na linię —
każda dostaje własny, przypisany token.

## Struktura projektu

| Plik / katalog             | Rola                                                          |
|-----------------------------|----------------------------------------------------------------|
| `test_wiedzy_app.py`        | Aplikacja Flask — trasy uczestnika i panelu administracyjnego |
| `db.py`                     | Dostęp do bazy SQLite, schemat, migracje                       |
| `importuj_pytania.py`       | CLI: import pytań z `.xlsx` jako nowy test                     |
| `generuj_tokeny.py`         | CLI: generowanie tokenów dostępu                                |
| `serwer_produkcyjny.py`     | Start appki przez Waitress                                     |
| `templates/`, `static/`     | Widoki (Jinja) i style                                         |
| `web_app.bat`                | Start deweloperski (Windows)                                   |
| `web_app_produkcja.bat`     | Start produkcyjny przez Waitress (Windows)                     |

## Dane i prywatność

Baza danych (`baza.db`), klucz sesji (`.flask_secret_key`), hasło administratora
(`.admin_haslo`) oraz pliki `.xlsx` z pytaniami są w `.gitignore` i nigdy nie trafiają
do repozytorium — każda instalacja generuje je lokalnie przy pierwszym starcie.

### Kopia zapasowa bazy

W panelu (`/admin`) przycisk **„Pobierz kopię bazy”** pobiera spójną kopię całej bazy
jako plik `baza-RRRR-MM-DD-GGMM.db` — można to robić w trakcie działania aplikacji.

Przywrócenie kopii:

1. Zatrzymaj aplikację (zamknij okno `web_app*.bat` / proces serwera).
2. Na wszelki wypadek zmień nazwę obecnego `baza.db` (np. na `baza.db.przed-przywroceniem`).
3. Usuń pliki `baza.db-wal` i `baza.db-shm`, jeśli istnieją — należą do starej bazy.
4. Skopiuj pobraną kopię do katalogu aplikacji i zmień jej nazwę na `baza.db`.
5. Uruchom aplikację ponownie.
