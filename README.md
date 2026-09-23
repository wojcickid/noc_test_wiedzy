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
  tokenów (anonimowo albo z listy uczestników — wklejonej lub z pliku `.xlsx`/`.csv`)
  oraz podglądu wyników zbiorczych i szczegółowych.
- Wysyłka zaproszeń i przypomnień mailem (SMTP, np. Gmail) albo przez korespondencję
  seryjną w Wordzie; link w mailu ma od razu wpisany token.
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

`uczestnicy.txt` to zwykły plik tekstowy, jedna osoba na linię w formacie
`Imię Nazwisko;e-mail` (albo samo imię, albo sam e-mail) — każda dostaje własny,
przypisany token. Zamiast `.txt` można podać plik `.xlsx` lub `.csv` z nagłówkami
kolumn `imie` i/lub `email` w pierwszym wierszu (jak przy imporcie w panelu).

## Lista uczestników

Na stronie tokenów testu listę osób można wkleić (jedna na linię: `Jan Kowalski;jan@firma.pl`,
separatorem może być też przecinek albo tabulator, adres może być w `<…>`) albo wgrać
jako plik `.xlsx`/`.csv`. W pliku pierwszy wiersz to nagłówki — rozpoznawane są m.in.
`imie`, `imię`, `imię i nazwisko`, `uczestnik` oraz `email`, `e-mail`, `mail`. CSV
z Excela (kodowanie Windows-1250 albo UTF-8, separator `;` lub `,`) jest obsługiwany.
Przy błędzie (zły adres, powtórzony adres, więcej niż 500 osób) nic nie jest generowane,
a lista zostaje w formularzu do poprawienia. Imię i e-mail można potem zmienić w wierszu
tokenu — zmiana adresu zeruje status wysłanego maila.

## Wysyłka maili

W panelu: **Test → „Maile do uczestników”**. Stamtąd idą zaproszenia (do osób, którym
jeszcze nie wysłano maila) i przypomnienia (do wszystkich, którzy nie ukończyli testu).
Pojedyncze osoby można zaznaczyć na liście tokenów i wysłać im zaproszenie ponownie.
Treść maili (temat i tekst, ze znacznikami typu `{imie}`, `{link}`, `{token}`) można
zmienić dla każdego testu — obok jest podgląd. Link w mailu ma wpisany token
(`/?token=…`), więc uczestnik klika i od razu startuje.

Maile idą w tle, jeden na sekundę; postęp i wynik każdego maila widać na stronie
wysyłki, a potem w kolumnie „Mail” na liście tokenów. **„Wysłano” oznacza, że serwer
poczty nadawcy przyjął wiadomość.** Jeśli adres jest literówką w domenie firmowej,
serwer czasem odrzuci go od razu (wtedy token dostaje status „błąd”), ale zwykle
zwrotka („Mail Delivery Subsystem” / „Undeliverable”) przychodzi dopiero później na
skrzynkę nadawcy — aplikacja jej nie widzi, więc po wysyłce warto tam zajrzeć.

### Ustawienia serwera poczty (`config.json`)

1. Skopiuj [`config.przyklad.json`](config.przyklad.json) jako `config.json` w katalogu
   aplikacji (plik jest w `.gitignore` — hasło nigdy nie trafia do repozytorium).
2. Uzupełnij `login`, `haslo` i `nadawca_email` (zwykle ten sam adres co login).
3. W panelu: **„Ustawienia poczty”** — sprawdź podgląd (bez hasła), ustaw nazwę nadawcy
   i **adres aplikacji**, a potem wyślij mail testowy do siebie.

Adres aplikacji to adres, pod którym uczestnicy otwierają test w sieci firmowej
(np. `http://192.168.1.10:5555`) — trafia do linków w mailach. Domyślny
`http://localhost:5555` działa tylko na komputerze z serwerem, panel ostrzega o tym.

**Gmail / Google Workspace** (`smtp.gmail.com`, port `587`, `starttls`):

- Zwykłe hasło do konta nie zadziała — potrzebne jest **hasło do aplikacji**. Włącz
  weryfikację dwuetapową na koncie, potem na <https://myaccount.google.com/apppasswords>
  utwórz hasło (nazwa np. „Test wiedzy”) i wklej 16 znaków do `haslo` w `config.json`.
- W Google Workspace hasła do aplikacji musi dopuszczać administrator domeny
  (i weryfikacja dwuetapowa musi być włączona dla konta).
- Limity Google: ok. 500 odbiorców dziennie dla zwykłego Gmaila, ok. 2000 dla Workspace.

**Microsoft 365 / Outlook** (`smtp.office365.com`, port `587`, `starttls`): wymaga, żeby
administrator włączył dla skrzynki „uwierzytelniony SMTP” (SMTP AUTH). Microsoft wycofuje
logowanie hasłem do SMTP, więc w wielu firmach to nie zadziała — wtedy użyj korespondencji
seryjnej w Wordzie (niżej) albo konta Google.

### Korespondencja seryjna w Wordzie

Alternatywa bez `config.json`: na stronie „Maile do uczestników” przycisk **„Pobierz listę
do korespondencji (.xlsx)”** daje plik z kolumnami `imie`, `email`, `token`, `link`,
`nazwa_testu`, `dostepny_do`, `limit_czasu` (osoby z adresem, które nie ukończyły testu).
W Wordzie: *Korespondencja → Rozpocznij korespondencję seryjną → Wiadomości e-mail →
Wybierz adresatów → Użyj istniejącej listy* (wskaż plik), wstaw pola przez *Wstaw pole
scalania*, na końcu *Zakończ i scal → Wyślij wiadomości e-mail* (pole „Do”: `email`).
Wymaga klasycznego Outlooka na komputerze — nowy Outlook i Outlook w przeglądarce tego
nie obsługują. Aplikacja nie zna statusu takiej wysyłki.

## Wynik jednej osoby

Na stronie wyniku tokenu (klik w token na liście tokenów) przycisk **„Pobierz wynik tej
osoby (.xlsx)”** daje plik z danymi osoby, wynikiem, zaliczeniem i listą wszystkich pytań
(także tych bez odpowiedzi, gdy minął czas) z poprawnymi odpowiedziami i wyjaśnieniami.

## Struktura projektu

| Plik / katalog             | Rola                                                          |
|-----------------------------|----------------------------------------------------------------|
| `test_wiedzy_app.py`        | Aplikacja Flask — trasy uczestnika i panelu administracyjnego |
| `db.py`                     | Dostęp do bazy SQLite, schemat, migracje                       |
| `poczta.py`                 | Wysyłka maili przez SMTP (ustawienia z `config.json`)          |
| `config.przyklad.json`      | Wzór `config.json` z ustawieniami serwera poczty               |
| `importuj_pytania.py`       | CLI: import pytań z `.xlsx` jako nowy test                     |
| `generuj_tokeny.py`         | CLI: generowanie tokenów dostępu                                |
| `serwer_produkcyjny.py`     | Start appki przez Waitress                                     |
| `templates/`, `static/`     | Widoki (Jinja) i style                                         |
| `web_app.bat`                | Start deweloperski (Windows)                                   |
| `web_app_produkcja.bat`     | Start produkcyjny przez Waitress (Windows)                     |

## Dane i prywatność

Baza danych (`baza.db`), klucz sesji (`.flask_secret_key`), hasło administratora
(`.admin_haslo`), ustawienia poczty z hasłem (`config.json`) oraz pliki `.xlsx`
z pytaniami są w `.gitignore` i nigdy nie trafiają
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
