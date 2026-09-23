# Test wiedzy — przegląd kodu i plan poprawek

> Stan kodu: commit `73d3f77` (main). Numery linii w odnośnikach odnoszą się do tego commita.
> Dokument powstał z samego czytania kodu, niczego nie uruchamiano ani nie zmieniano.

Oznaczenia używane dalej w planie:
**B** błąd · **UI** interfejs · **L** logika · **S** stack · **F** nowa funkcja · **E** dodatkowa propozycja

---

## 0. Instrukcja dla Claude Code

> Ta sekcja jest dla agenta (Claude Code), który będzie wdrażał plan. Człowiek (właściciel projektu, dalej „user”) wskazuje na początku sesji numer etapu, np. *„zrób etap 2 z PLAN_POPRAWEK.md”*.

### 0.1. Zasady ogólne

1. **Jeden etap na jedną sesję.** Nie wychodź poza zakres wskazanego etapu (sekcja 7). Jeśli po drodze znajdziesz coś spoza zakresu, dopisz to do sekcji 0.5 „Znalezione po drodze”, zamiast poprawiać.
2. **Przed startem:**
   - przeczytaj cały ten plik i pozycje (B/UI/L/S/F/E) przypisane do etapu,
   - przeczytaj aktualny kod, bo numery linii w planie odnoszą się do commita `73d3f77` i mogły się przesunąć (zawsze weryfikuj, nie ufaj im na ślepo),
   - sprawdź `git status`: jeśli są niezacommitowane zmiany, zapytaj usera, co z nimi zrobić,
   - sprawdź w tabeli 0.4, czy poprzednie etapy są ukończone. Etapy 2+ zakładają ukończony etap 0 (testy + `base.html`), etapy 4 i 6 zakładają etap 2.
3. **Zadaj pytania z sekcji 0.3 dla danego etapu naraz, w jednej wiadomości**, zanim zaczniesz pisać kod. Nie zgaduj odpowiedzi na pytania o zachowanie aplikacji. Jeśli user odpowie „zdecyduj sam”, wybierz rekomendację z planu i zapisz decyzję w sekcji 0.5.
4. **Gałąź:** pracuj na nowej gałęzi `etap-<N>-<krotki-opis>` (np. `etap-2-podejscia-w-bazie`), nie na `main`. **Nie rób push ani merge bez wyraźnej zgody usera.**
5. **Styl kodu:** dopasuj się do istniejącego kodu: polskie nazwy identyfikatorów i komentarzy, podobna gęstość komentarzy, SQL pisany ręcznie (bez ORM), funkcje dostępu do bazy w `db.py`, trasy w `test_wiedzy_app.py`. **Nowe zależności w `requirements.txt` tylko po zgodzie usera.**
6. **Dane usera:**
   - przed każdą zmianą schematu bazy zrób kopię: `baza.db` → `baza.db.bak-<data>`,
   - migracje dopisuj do `_migruj_tabele` (`db.py`) tak, żeby istniejąca baza migrowała się sama przy starcie i żeby migracja była idempotentna,
   - przetestuj migrację na **kopii** istniejącej bazy, jeśli jest dostępna,
   - nigdy nie usuwaj `baza.db`, `.admin_haslo`, `.flask_secret_key` ani plików `.xlsx`.
7. **Sekrety:** hasła SMTP i inne poświadczenia trzymaj tylko w plikach dodanych do `.gitignore`. Nie wypisuj ich w logach, commitach ani odpowiedziach.
8. **Testy:**
   - każda zmiana zachowania ma test w `pytest` (`app.test_client()`, tymczasowa baza przez podmianę `db.DB_PLIK`),
   - etap jest skończony dopiero wtedy, gdy `pytest` przechodzi w całości,
   - jeśli test nie przechodzi, powiedz to wprost i pokaż wynik; nie osłabiaj testu, żeby przeszedł.
9. **Uruchomienie:** po zmianach uruchom aplikację (`python test_wiedzy_app.py` albo `serwer_produkcyjny.py`) i sprawdź, że startuje bez błędów na istniejącej bazie.

### 0.2. Zakończenie etapu (definition of done)

Na koniec sesji przedstaw userowi:
1. **Podsumowanie zmian:** które ID z planu zrobione, które nie i dlaczego.
2. **Wynik `pytest`** (liczba testów, czy wszystkie przeszły).
3. **Listę do ręcznego sprawdzenia w przeglądarce**, konkretną, krok po kroku (np. *„wystartuj test tokenem, zamknij kartę po 2. pytaniu, otwórz ponownie i wpisz ten sam token, powinieneś wrócić do pytania 3”*). Sekcja 0.3 podaje minimum dla każdego etapu.
4. **Propozycję wiadomości commita** z listą ID (np. `Etap 2: postęp testu w bazie (L1, L2, L3, B1, B8, B9, B13)`), z polskim opisem.
5. **Commit dopiero po akceptacji usera.**
6. **Aktualizację tego pliku:** status etapu w tabeli 0.4, decyzje i znaleziska w 0.5, ewentualne zmiany planu.

### 0.3. Pytania do usera i ręczne testy, etap po etapie

**Etap 0: przygotowanie**
- Pytania:
  - Jaka wersja Pythona jest na docelowej maszynie?
  - Czy istnieje `baza.db` z prawdziwymi danymi, którą trzeba zachować? Jeśli tak, poproś o kopię do testów migracji.
  - Czy wersje w `requirements.txt` przypiąć do tego, co jest teraz w `.venv` (`pip freeze`), czy do najnowszych?
- Ręcznie: wygląd wszystkich stron po przejściu na `base.html` ma być **identyczny** jak wcześniej (to refaktor, nie zmiana wyglądu).

**Etap 1: szybkie poprawki**
- Pytania:
  - CSRF: Flask-WTF (nowa zależność) czy własny prosty token w sesji? *Rekomendacja: własny token, bez nowej zależności.*
  - Czy tryb debug może nasłuchiwać tylko na `127.0.0.1`? Wtedy nie będzie dostępny z innych komputerów w sieci.
- Ręcznie: logowanie admina, generowanie tokenów + F5 (nie może powstać druga partia), komunikaty w kolorach, strona na telefonie.

**Etap 2: przebudowa przebiegu testu** (najbardziej ryzykowny, zachowaj szczególną ostrożność przy migracji)
- Pytania:
  - Wznowienie testu: czy uczestnik może kontynuować na **innym** urządzeniu, podając ten sam token? *Rekomendacja: tak, token jest jedynym kluczem.*
  - Reset tokenu przez admina: czy usuwać poprzednie odpowiedzi, czy archiwizować je (np. jako „podejście 1”)?
  - Czy w chwili wdrożenia może trwać jakiś test? Aktywne sesje plikowe przepadną, więc wdrożyć trzeba, gdy nikt nie pisze testu.
  - Czy są już zduplikowane odpowiedzi w bazie? Sprawdź zapytaniem i pokaż wynik przed założeniem `UNIQUE`.
- Ręcznie:
  - pełny test od startu do wyniku,
  - zamknięcie karty w połowie i wznowienie,
  - wznowienie na innej przeglądarce,
  - podwójne kliknięcie „Rozpocznij” i „Zakończ test”,
  - reset tokenu w panelu,
  - statusy tokenów w panelu.

**Etap 3: import**
- Pytania:
  - Plik z błędnymi wierszami: odrzucać cały plik czy pozwolić zaimportować tylko poprawne wiersze?
  - Czy potrzebny jest ekran podglądu przed zatwierdzeniem importu?
  - Czy już teraz dodać opcjonalną kolumnę `wyjasnienie` (E4)?
- Ręcznie: import prawdziwego pliku z pytaniami, pliku z pustą komórką, pliku ze złą literą odpowiedzi i pliku z nagłówkami o innej wielkości liter. Sprawdzić też szablon do pobrania.

**Etap 4: kontrola nad testem (F1, F2, E14)**
- Pytania:
  - Domyślny tryb szczegółów dla nowych testów? *Rekomendacja: `po_zamknieciu`.*
  - Domyślny wynik punktowy: od razu czy razem ze szczegółami?
  - Czy admin może zmienić limit czasu lub tryb szczegółów, gdy test już trwa? Jeśli tak, czy zmiana dotyczy trwających podejść?
  - Gdy czas się skończy, a uczestnik ma zaznaczoną, ale niewysłaną odpowiedź: liczyć ją czy nie? *Rekomendacja: liczyć, formularz wysyła się automatycznie.*
  - Tolerancja po terminie (proponowane 5 s)?
  - Treść ekranu startowego z zasadami: czy user ją poda, czy zaproponować?
  - Strefa czasowa i format dat do wyświetlania?
- Ręcznie:
  - licznik czasu (ustawić limit na 1 min) i automatyczne zakończenie,
  - powrót po terminie,
  - każdy tryb szczegółów w `/wynik` i `/sprawdz-wynik`,
  - „Zamknij test i opublikuj”,
  - okno dostępności: start przed i po terminie,
  - widok na telefonie.

**Etap 5: eksporty i raporty**
- Pytania:
  - Jakie kolumny w eksporcie wyników? Czy dołączać imiona i maile?
  - Domyślny próg zaliczenia? (puste = brak)
  - Czy uczestnik widzi informację zdał/nie zdał?
- Ręcznie: otworzyć wyeksportowane pliki w Excelu (polskie znaki, daty), statystyki pytań na teście z kilkoma wynikami, pobranie kopii bazy.

**Etap 6: maile**
- Pytania:
  - Co odpowiedziało IT: skrzynka z SMTP AUTH w M365, relay, Google Workspace czy odmowa? Przy odmowie wdrażasz **plan B** z F3.
  - Adres i nazwa nadawcy?
  - Adres, pod którym uczestnicy wchodzą na aplikację (potrzebny do linku w mailu)?
  - Treść domyślnego szablonu maila: poda user czy zaproponować?
  - Czy import listy uczestników ma przyjmować CSV/XLSX, czy wystarczy lista wklejana w polu tekstowym (`Imię Nazwisko;email`)?
- Ręcznie:
  - mail testowy do siebie,
  - wysyłka do 2–3 adresów testowych,
  - kliknięcie linku z maila (token nie może się zużyć przed kliknięciem „Rozpocznij”),
  - status wysyłki przy tokenie,
  - zachowanie przy błędnym haśle SMTP (czytelny komunikat, bez wycieku hasła).

**Etap 7+**
- Pytania: które pozycje E wybrać i w jakiej kolejności. Przedstaw krótko koszt i wartość z tabel w sekcji 6.

### 0.4. Status etapów

Aktualizuj tę tabelę na końcu każdej sesji.

| Etap | Status | Gałąź / commit | Data | Uwagi |
|------|--------|----------------|------|-------|
| 0 Przygotowanie | zrobione (czeka na akceptację) | `etap-0-testy-i-baza-html` | 2026-09-23 | S4, S5, UI2 — patrz sekcja 0.5 |
| 1 Szybkie poprawki | do zrobienia | | | |
| 2 Przebieg testu w bazie | do zrobienia | | | |
| 3 Import | do zrobienia | | | |
| 4 Kontrola nad testem | do zrobienia | | | |
| 5 Eksporty i raporty | do zrobienia | | | |
| 6 Maile | do zrobienia (zapytanie do IT: nie wysłane) | | | |
| 7+ Rozwój | do zrobienia | | | |

### 0.5. Decyzje i znalezione po drodze

Dopisuj tu decyzje usera (z datą i etapem) oraz problemy spoza zakresu bieżącego etapu.

**Etap 0 (2026-09-23):**

- **Python:** docelowa maszyna to 3.11.2. Na tym komputerze nie było 3.11 w ogóle (tylko 3.10/3.12/3.14) — zainstalowano przez `winget install Python.Python.3.11`, co dało **3.11.9** (winget trzyma tylko najnowszą łatkę danej linii, nie starsze patch-e). Różnica 3.11.2 → 3.11.9 to wyłącznie poprawki błędów, bez zmian API — user zaakceptował to ryzyko. `.venv` przebudowane pod 3.11.9. Stare `.venv` (Python 3.10.10, `.venv-stary-310/`) **skasowane** na wyraźną prośbę usera ("nie powinno być problemu, a jak będą to naprawimy").
- **requirements.txt:** user wybrał najnowsze dostępne wersje (nie `pip freeze` z istniejącego `.venv`). Efekt: **pandas 2.2.0 → 3.0.6** i **numpy → 2.4.6** (duży skok major/minor), Flask 3.0.2 → 3.1.3, openpyxl 3.1.2 → 3.1.5. Wszystkie 26 testów z S4 przechodzi na tych wersjach — nic nie pękło, ale warto to mieć na uwadze przy kolejnych etapach (szczególnie import przez pandas w Etapie 3). Dodano `requirements-dev.txt` (pytest, tylko do testów, nie na produkcję).
- **baza.db:** zastana baza (test „Przykładowy test", 5 pytań/2 tokeny/10 odpowiedzi) potwierdzona przez usera jako dane testowe. Zrobiono kopię (`baza.db.bak-2026-09-23`) przed zmianami zgodnie z zasadą 0.1.6, a na koniec etapu **oba pliki (`baza.db` i kopia) skasowane** na wyraźną prośbę usera ("wywal tą testową bazę") — appka sama utworzy pustą bazę przy następnym starcie.
- **Odstępstwo od zasady 0.1.6:** podczas pisania i uruchamiania testów `baza.db` była kilkukrotnie kasowana/tworzona od nowa (żeby zresetować stan między ręcznymi sprawdzeniami) — zasada mówi „nigdy nie usuwaj baza.db". Zrobione świadomie, bo user jawnie określił tę bazę jako nieważne dane testowe i kopia zapasowa istniała przez cały czas (do momentu, aż user sam polecił ją skasować, patrz wyżej). **Przy kolejnych etapach, gdy w bazie będą realne dane uczestników, tej zasady należy pilnować bez wyjątków.**
- **Znane ograniczenie (poza zakresem Etapu 0):** `test_wiedzy_app.py` przy imporcie modułu (czyli też przy starcie `pytest`) czyta/tworzy prawdziwe pliki projektu `.flask_secret_key` i `.admin_haslo` (nie są w pełni izolowane dla testów, w przeciwieństwie do `db.DB_PLIK` i `SESSION_DIR`, które fixture `klient` poprawnie podmienia). Nie jest to błąd — pliki są gitignored i nieszkodliwe do nadpisania — ale docelowo naturalnie rozwiąże to S6 (konfiguracja w jednym miejscu, wstrzykiwana zamiast czytana z globalnych stałych przy imporcie modułu).
- **UI2 — weryfikacja identyczności wyglądu:** zamiast (albo obok) ręcznego sprawdzenia w przeglądarce, napisano skrypt porównujący wyrenderowany HTML wszystkich stron (stare szablony z `main` vs. nowe po `base.html`) przy deterministycznych danych — zero różnic poza białymi znakami. Wynik: **brak jakichkolwiek różnic wizualnych/strukturalnych.**

---

## Spis treści

0. [Instrukcja dla Claude Code](#0-instrukcja-dla-claude-code)
1. [Błędy](#1-błędy)
2. [UI](#2-ui)
3. [Logika](#3-logika)
4. [Stack technologiczny](#4-stack-technologiczny)
5. [Nowe funkcje (zamówione)](#5-nowe-funkcje-zamówione)
   - F1 Limit czasu z licznikiem
   - F2 Kiedy dostępne są odpowiedzi
   - F3 Wysyłka maili z tokenem
6. [Dodatkowe propozycje](#6-dodatkowe-propozycje)
7. [Kolejność wdrażania](#7-kolejność-wdrażania)
8. [Docelowe zmiany w schemacie bazy](#8-docelowe-zmiany-w-schemacie-bazy)

---

## 1. Błędy

### Poważne

| ID | Problem | Gdzie | Poprawka |
|----|---------|-------|----------|
| B1 | **Token przepada, gdy uczestnik straci sesję.** Token jest zużywany przy starcie, a odpowiedzi zapisują się do bazy dopiero na końcu. Postęp żyje wyłącznie w pliku sesji, powiązanym z ciasteczkiem, które wygasa po zamknięciu przeglądarki. Zamknięcie karty, restart telefonu albo zmiana urządzenia oznaczają spalony token i utracone odpowiedzi. Admin nie ma jak tokenu zresetować. | `test_wiedzy_app.py:151`, `:250-257` | Postęp w bazie, zapis po każdej odpowiedzi, wznowienie tym samym tokenem, reset tokenu przez admina (patrz L1, L2). |
| B2 | **Open redirect przy logowaniu admina.** `nastepny` z URL trafia do `redirect()` bez sprawdzenia, więc `/admin/login?nastepny=https://obca-strona` wyprowadza poza aplikację. | `test_wiedzy_app.py:312` | Akceptować tylko ścieżki względne: zaczynające się od `/`, ale nie od `//`. |
| B3 | **Brak ochrony CSRF** na wszystkich formularzach POST admina (import, tokeny, przypisania, wylogowanie). | wszystkie formularze admina | Flask-WTF `CSRFProtect` albo własny token w sesji i ukryte pole w formularzach. |
| B4 | **`FLASK_DEBUG=1` razem z `host="0.0.0.0"`** wystawia debugger Werkzeuga na sieć LAN, co daje zdalne wykonanie kodu. | `test_wiedzy_app.py:535-536` | W trybie debug nasłuchiwać tylko na `127.0.0.1`. |

### Średnie

| ID | Problem | Gdzie | Poprawka |
|----|---------|-------|----------|
| B5 | **Import zapisuje puste komórki jako `"nan"`.** Do tego liczby w kolumnie z pustą komórką stają się floatami, więc `5` zapisuje się jako `"5.0"`. | `db.py:185-190` | Czytać przez openpyxl (S1) albo `dtype=str` + `fillna("")`, a puste pola odrzucać walidacją (B6). |
| B6 | **Brak walidacji treści przy imporcie.** `odpowiedz` może mieć wartość spoza A–D (`E`, `1`, `nan`) i wtedy na pytanie nie da się odpowiedzieć poprawnie. Nazwy kolumn muszą się zgadzać znak w znak, więc `Tresc_pytania` albo spacja na końcu dają błąd. | `db.py:158-162` | Normalizować nagłówki (`strip().lower()`). Walidować każdy wiersz i zwracać raport w stylu „wiersz 7: pusta opcja_c; wiersz 12: odpowiedź 'E'”. |
| B7 | **Brak walidacji odpowiedzi uczestnika.** Z formularza przyjdzie dowolny string i trafi do bazy. `int(pytanie_id)` dla wartości nieliczbowej kończy się błędem 500. | `test_wiedzy_app.py:196-204` | `odpowiedz in {"A","B","C","D"}`, `pytanie_id.isdigit()`. |
| B8 | **Race condition przy zapisie wyniku.** SELECT „czy już zapisane” i INSERT są rozdzielone, a w tabeli brakuje `UNIQUE(token, pytanie_id)`. Podwójne kliknięcie „Zakończ test” może zapisać odpowiedzi dwa razy i zawyżyć wynik. | `test_wiedzy_app.py:247-257` | Dodać `UNIQUE(token, pytanie_id)` + `INSERT OR IGNORE`. Docelowo wystarczy zapis po każdej odpowiedzi (L1). |
| B9 | **Podwójne kliknięcie „Rozpocznij test” pokazuje fałszywy błąd.** Pierwsze żądanie zużywa token, drugie dostaje „już wykorzystany”. Uczestnik widzi błąd, chociaż test już ruszył. | `test_wiedzy_app.py:151-154` | Jeśli token jest zużyty, ale podejście trwa, przekierować do `/test` (wznowienie z L1). |
| B10 | **F5 po wygenerowaniu tokenów tworzy kolejną partię.** Po POST strona jest renderowana bez przekierowania (brak wzorca Post/Redirect/Get). | `test_wiedzy_app.py:455-496` | Po POST przekierowanie na GET. Nowe tokeny pokazać przez `?partia=<id>` albo przez sesję. |
| B11 | **Nieskończona pętla w CLI `generuj_tokeny.py`.** Pojawia się przy `--dlugosc 0`, `--dlugosc 1` z więcej niż 31 tokenami, ogólnie gdy żądana liczba przekracza pulę możliwych kodów. `--dlugosc` nie jest walidowane, a pętla nie ma limitu prób. | `generuj_tokeny.py:21`, `db.py:209-212` | Walidować 4–20 tak jak w panelu. Dodać limit prób w pętli. |
| B12 | **Pętla przekierowań `/test` ↔ `/wynik`**, gdy test nie ma pytań. Przez import taki test dziś nie powstanie, ale kod tego przypadku nie zabezpiecza. | `test_wiedzy_app.py:176-215` | Przy pustej puli pytań wyświetlić komunikat zamiast przekierowania. |

### Drobne

| ID | Problem | Gdzie |
|----|---------|-------|
| B13 | Katalog `flask_session/` nigdy nie jest czyszczony, porzucone sesje zostają na dysku. Znika razem z L1. | `test_wiedzy_app.py:108-122` |
| B14 | Wstecz w przeglądarce + „Dalej” pokazuje „Zaznacz odpowiedź”, chociaż odpowiedź była zaznaczona. Prawdziwy powód to niezgodność `pytanie_id`. Potrzebny osobny komunikat, np. „To pytanie zostało już zapisane”. | `test_wiedzy_app.py:200-202` |
| B15 | `admin_przypisz_token` przekazuje `test_id` z formularza wprost do `url_for`. Wartość nieliczbowa daje błąd 500. | `test_wiedzy_app.py:503-509` |
| B16 | `admin_test` filtruje wyniki po nazwie testu, a nie po `id`. Działa tylko dlatego, że nazwa jest unikalna. Widok `zbiorcze_wyniki` powinien zwracać `test_id`. | `test_wiedzy_app.py:435`, `db.py:91-104` |
| B17 | README twierdzi, że szablon generuje `importuj_pytania.py --help`, co jest nieprawdą. Pomija też, że po zmianie `.admin_haslo` trzeba zrestartować aplikację. | `README.md:51` |
| B18 | `importuj_pytania.py` nie łapie błędów `read_excel`, więc uszkodzony plik kończy się surowym tracebackiem. | `importuj_pytania.py:30` |
| B19 | Import: najpierw sprawdzenie „czy nazwa istnieje”, potem INSERT. Przy wyścigu `IntegrityError` daje 500. Wystarczy złapać `sqlite3.IntegrityError`. | `db.py:167-173` |
| B20 | Szczegóły tokenu bez wyników przekierowują do głównego panelu zamiast z powrotem do testu. | `test_wiedzy_app.py:519-521` |

---

## 2. UI

| ID | Problem / sugestia | Priorytet |
|----|-------------------|-----------|
| UI1 | **Brak `<meta name="viewport" content="width=device-width, initial-scale=1">`** w żadnym szablonie, przez co na telefonie strona wyświetla się w pomniejszeniu. Uczestnicy często używają telefonów. | wysoki |
| UI2 | **Szablon bazowy `base.html`.** `<head>`, blok flash, nawigacja admina i stopka są skopiowane w 10 plikach. `{% extends %}` usuwa ok. 40% kodu szablonów i ułatwia wszystkie dalsze zmiany. | wysoki (robić przed resztą UI) |
| UI3 | **Każdy link wygląda jak niebieski przycisk**, także linki w tabelach, bo globalny styl `a {}` jest w `style.css:71`. Wygląd przycisku przenieść do klasy `.btn`. | wysoki |
| UI4 | **Wszystkie komunikaty flash są czerwone**, także sukcesy. Wprowadzić kategorie `flash(msg, "ok"/"blad"/"info")` z trzema kolorami. | średni |
| UI5 | **Test: brak liter A/B/C/D przy opcjach**, choć wyniki pokazują „B) Warszawa”. Opcje są wyśrodkowane i pogrubione (`label` ma `display:block; bold`, `body` ma `text-align:center`). Lepiej zrobić duże, klikalne kafelki wyrównane do lewej, z literą i obsługą klawiszy 1–4 / A–D. | wysoki |
| UI6 | **Pasek postępu** zamiast samego tekstu „Pytanie 3 z 20”. Nazwa testu w nagłówku i w `<title>` zamiast „Test”. | średni |
| UI7 | **Strona wyniku:** dodać procent, informację zdał/nie zdał (F-extra) i wskazówkę „wynik i szczegóły sprawdzisz później pod /sprawdz-wynik swoim tokenem” (albo informację od kiedy, patrz F2). | średni |
| UI8 | **Tokeny:** wykorzystany token jest czerwony („zle”), wolny zielony („ok”), co wprowadza w błąd. Zastąpić neutralnym tłem i znacznikiem statusu: *wolny / w trakcie / ukończony / czas minął*. | średni |
| UI9 | **Tokeny:** przycisk „Kopiuj wszystkie” (schowek, format `imię<TAB>token`) i eksport CSV. Link do strony tokenów widoczny bezpośrednio w wierszu testu w panelu. | średni |
| UI10 | **Wyniki:** eksport do XLSX/CSV (zbiorczy i szczegółowy). openpyxl jest już w zależnościach. | średni |
| UI11 | **Potwierdzenie przed „Zakończ test”**, w tym informacja o liczbie pytań bez odpowiedzi, jeśli pojawi się pomijanie pytań. | niski |
| UI12 | **Drobiazgi:** zahardkodowane `href="/"` / `action="/"` zamieniamy na `url_for`; zdublowany link „Zaimportuj nowy test” w panelu; brak `autofocus` w polu tokenu i hasła. | niski |

---

## 3. Logika

| ID | Sugestia |
|----|----------|
| L1 | **Postęp testu w bazie zamiast w plikach sesji.** Nowa tabela `podejscia` (token, wylosowane pytania, indeks, start, termin, koniec, status), a każda odpowiedź zapisuje się do `odpowiedzi_uzytkownika` od razu po kliknięciu „Dalej”. Rozwiązuje B1, B8, B9, B13, daje wznowienie testu na innym urządzeniu i pozwala adminowi widzieć, kto jest w trakcie. **To fundament pod F1 i F2.** |
| L2 | **Akcje admina na tokenach:** reset (ponowne podejście), unieważnienie, usunięcie. Na testach: usuń, duplikuj, zamknij/otwórz. |
| L3 | **Mianownik wyniku = liczba wylosowanych pytań**, a nie `COUNT(*)` udzielonych odpowiedzi (`db.py:96-98`). Dziś to się pokrywa, ale po wprowadzeniu limitu czasu (F1) pytania bez odpowiedzi zawyżałyby procent. |
| L4 | **Losowa kolejność opcji A–D** dla każdego uczestnika. Mapowanie liter trzeba przechowywać w `podejscia`, żeby ocena i podgląd pokazywały właściwe litery. |
| L5 | **Walidacja importu z raportem błędów** per wiersz (B5, B6) i **podgląd przed zatwierdzeniem**: „wczytano 40 pytań, 2 z błędami — popraw albo pomiń”. |
| L6 | **Rozdzielenie pola `przypisany`** na `imie` i `email`. Wysyłka maili (F3) wymaga pewnego adresu, a dziś to dowolny tekst. Import listy w formacie `Imię Nazwisko;email` albo z pliku CSV/XLSX. |
| L7 | **`/sprawdz-wynik` pokazuje poprawne odpowiedzi każdemu, kto zna token**, więc bank pytań „wycieka” do kolejnych osób. Rozwiązanie: F2. |

---

## 4. Stack technologiczny

**Ocena ogólna:** Flask + SQLite (WAL) + Waitress + Jinja **ma sens** dla wewnętrznego narzędzia uruchamianego na Windowsie. Jest prosty, nie wymaga serwera bazy i spokojnie obsłuży kilkudziesięciu uczestników jednocześnie. Nie ma powodu przechodzić na nic cięższego (Django, Postgres, SPA).

| ID | Zmiana |
|----|--------|
| S1 | **Usunąć pandas.** Służy tylko do `read_excel`/`to_excel`, a ciągnie numpy i ok. 100 MB zależności. Samo `openpyxl` wystarczy i przy okazji usuwa problemy z `"nan"` i `"5.0"` (B5). |
| S2 | **Usunąć ręczne sesje plikowe**, bo stan przechodzi do bazy (L1). W ciasteczku zostaje tylko token/ID podejścia, które i tak jest podpisane przez Flask. |
| S3 | **CSRF:** Flask-WTF (`CSRFProtect`) albo 15 linii własnego kodu. |
| S4 | **Testy `pytest`** z `app.test_client()` i bazą tymczasową. Minimum: start → odpowiedzi → wynik; import poprawny i błędny; reset tokenu; limit czasu; widoczność wyników. |
| S5 | **`requirements.txt` z przypiętymi wersjami** (`Flask==3.x.y` itd.). Pliki `.bat` robią dziś `pip install` przy każdym starcie, co wymaga internetu. Instalować tylko przy tworzeniu `.venv` albo po zmianie `requirements.txt`. Oba `.bat` różnią się jedną linią, więc można je połączyć w jeden z parametrem. |
| S6 | **Konfiguracja w jednym miejscu:** plik `config.json` / `.env` (gitignored) z portem, adresem bazowym aplikacji (potrzebnym do linków w mailach), ustawieniami SMTP i strefą czasową, zamiast rozproszonych stałych i osobnych plików sekretów. |
| S7 | **Kopia zapasowa bazy:** przycisk w panelu „Pobierz kopię bazy” (`sqlite3` `backup()` do pliku), ewentualnie automatyczna kopia przy starcie. |

---

## 5. Nowe funkcje (zamówione)

### F1. Limit czasu na test z licznikiem

**Zależy od:** L1 (start i termin muszą być w bazie, a nie w przeglądarce).

**Panel admina:** w formularzu importu i w nowej stronie „Ustawienia testu” pole *Limit czasu (minuty)*. Puste pole oznacza brak limitu. Kolumna `testy.limit_czasu_min INTEGER NULL`.

**Zasada:** serwer jest jedynym źródłem prawdy, a licznik w przeglądarce tylko to wyświetla.

1. Przy starcie podejścia zapisać `rozpoczeto` i `termin = rozpoczeto + limit`.
2. Każdy GET `/test` liczy `pozostalo_s = termin − teraz` i przekazuje wartość do szablonu.
3. JS na stronie odlicza `mm:ss` (`setInterval` co 1 s). W ostatniej minucie licznik robi się czerwony. Przy 0 automatycznie wysyła formularz (bieżąca odpowiedź, jeśli zaznaczona) albo przechodzi na `/wynik`.
4. Serwer odrzuca odpowiedzi po `termin + 5 s` tolerancji i kończy podejście ze statusem `czas_minal`. Pytania bez odpowiedzi liczą się jako błędne (patrz L3).
5. Jeśli uczestnik zamknie kartę i wróci po terminie, pierwsze wejście kończy podejście. Panel admina też „leniwie” domyka przeterminowane podejścia przy wyświetlaniu listy, żeby statusy były aktualne.
6. Czas liczony od momentu startu, więc wznowienie na innym urządzeniu (L1) go nie resetuje.
7. Licznik oparty na różnicy względem czasu serwera, a nie na zegarze klienta: przy każdym ładowaniu strony serwer podaje `pozostalo_s`, a JS liczy od `performance.now()`.

**Na przyszłość (opcjonalnie):** limit na pojedyncze pytanie, przedłużenie czasu konkretnej osobie przez admina, np. dla osób z orzeczeniem.

**Admin widzi:** w tabeli wyników czas trwania podejścia i status *ukończony / czas minął*.

---

### F2. Kiedy dostępne są odpowiedzi (ochrona przed przekazywaniem odpowiedzi)

Dwa niezależne ustawienia na teście:

**a) Wynik punktowy** (`testy.wynik_widoczny`): *od razu po teście* (domyślnie) / *razem ze szczegółami*.

**b) Szczegóły, czyli poprawne odpowiedzi** (`testy.tryb_szczegolow`):

| Wartość | Znaczenie | Uwagi |
|---------|-----------|-------|
| `natychmiast` | od razu po ukończeniu (dzisiejsze zachowanie) | tylko dla testów ćwiczeniowych |
| `po_zamknieciu` | gdy admin kliknie **„Zamknij test i opublikuj odpowiedzi”** | **rekomendowane jako domyślne**, admin ma pełną kontrolę. Zamknięcie blokuje też nowe starty. |
| `od_daty` | od ustawionej daty i godziny (`testy.szczegoly_od`) | dobre przy teście z określonym terminem |
| `po_wszystkich` | gdy wszystkie wygenerowane tokeny mają status ukończony | **wymaga daty awaryjnej**, inaczej jedna nieobecna osoba blokuje wszystkich. W praktyce to wariant `od_daty` z wcześniejszym odblokowaniem. |
| `nigdy` | szczegóły widzi tylko admin | egzaminy, certyfikacje |

**Implementacja:** jedna funkcja `szczegoly_dostepne(test, teraz) -> (bool, komunikat)`, używana w `/wynik` i w `/sprawdz-wynik`. Gdy szczegóły są niedostępne, uczestnik widzi np. *„Szczegółowe odpowiedzi będą dostępne od 30.09 16:00”* albo *„…po zakończeniu testu przez prowadzącego”*. Sprawdzenie wyłącznie po stronie serwera, więc ukrycie w HTML nie wystarcza.

**Powiązane (mocno zalecane):** okno dostępności testu `dostepny_od` / `dostepny_do`. Poza oknem nie da się wystartować. W trybie `od_daty` domyślną datą publikacji jest wtedy `dostepny_do`.

---

### F3. Wysyłka maili z tokenem

#### Porównanie opcji

| | 1. `mailto:` (otwiera Outlooka) | 2. Automatyzacja Outlooka (pywin32/COM) | 3. SMTP (Google z hasłem aplikacji albo firmowy M365) |
|---|---|---|---|
| Wysyłka masowa | nie, każdy mail klikany osobno | tak | tak |
| Wymaga IT / poświadczeń | nie | nie | **tak, konto SMTP** |
| Działa z serwera (Waitress) | tak (to link w przeglądarce admina) | **tylko na tym samym komputerze i koncie, gdzie działa Outlook** | tak |
| Kruchość | brak | **wysoka:** „nowy Outlook” dla Windows nie obsługuje COM, pojawiają się ostrzeżenia bezpieczeństwa Outlooka, nie działa jako usługa | niska |
| Status wysyłki w panelu | nie | częściowo | tak (sukces lub błąd per adres) |
| Koszt wdrożenia | ok. 15 min | 1–2 dni + utrzymanie | ok. 1 dzień |

#### Rekomendacja: **opcja 3 w wersji ogólnej, czyli wysyłka przez SMTP** (`smtplib` z biblioteki standardowej, bez nowych zależności)

Uzasadnienie:
- Jedna implementacja działa z dowolnym serwerem pocztowym: firmowym M365 (`smtp.office365.com:587`, STARTTLS), firmowym relayem, Google Workspace z hasłem aplikacji. Zmienia się tylko konfiguracja.
- Opcja 2 odpada, bo Microsoft wycofuje klasycznego Outlooka na rzecz „nowego”, który nie ma COM, więc rozwiązanie przestałoby działać bez ostrzeżenia.
- **Nie używać prywatnego konta Gmail**: dane firmowe (imiona, maile pracowników) szłyby przez prywatne konto (RODO), a maile z Gmaila do firmowej domeny łatwo lądują w spamie. Konto Google ma sens tylko wtedy, gdy firma korzysta z Google Workspace.

**Warunek wstępny (do sprawdzenia przed wdrożeniem):** zapytać IT o jedno z dwóch:
(a) skrzynkę techniczną typu `test-wiedzy@…` z włączonym *SMTP AUTH* w M365, albo
(b) adres wewnętrznego relaya SMTP.

**Plan B, jeśli IT się nie zgodzi:** bez automatu.
1. Przycisk `mailto:` przy każdym tokenie z gotowym tematem i treścią (15 min pracy).
2. Eksport CSV (imię, email, token, link) i **korespondencja seryjna Word → Outlook**. Wysyła wszystkim naraz, spersonalizowane, z konta admina, bez żadnego kodu po stronie aplikacji.

#### Zakres funkcji (wariant SMTP)

- **Konfiguracja** w `config.json` (gitignored): host, port, STARTTLS, login, hasło, nadawca, adres bazowy aplikacji. W panelu przycisk **„Wyślij mail testowy do mnie”**.
- **Szablon maila** edytowalny per test: temat i treść z polami `{imie}`, `{token}`, `{link}`, `{nazwa_testu}`, `{dostepny_do}`, `{limit_czasu}`. Podgląd przed wysyłką.
- **Link z tokenem:** `https://<adres>/?token=ABCD2345` z uzupełnionym polem, uczestnik klika tylko „Rozpocznij”. Token nie jest zużywany samym wejściem na link, dopiero kliknięciem przycisku, bo skanery linków w poczcie otwierają URL-e automatycznie.
- **Wysyłka:** do zaznaczonych, do wszystkich niewysłanych albo ponownie do wybranych. Tempo ok. 1 mail/s (M365 ma limit 30 wiadomości/min), realizowane w wątku w tle ze stroną postępu.
- **Status per token:** `mail_wyslany_at`, `mail_status` (ok / błąd + treść błędu). Kolumna w tabeli tokenów.
- **Przypomnienie:** „wyślij przypomnienie do osób, które jeszcze nie ukończyły” (patrz E6).
- Wymaga L6 (osobne pole `email`).

---

## 6. Dodatkowe propozycje

Posortowane od największej wartości przy najmniejszym koszcie.

### Dla trenera / admina

| ID | Propozycja | Wartość | Koszt |
|----|-----------|---------|-------|
| E1 | **Eksport wyników do XLSX** (zbiorczo i szczegółowo, z nazwiskami). Najczęściej potrzebne po szkoleniu, do raportu dla przełożonych albo HR. | wysoka | niski |
| E2 | **Próg zaliczenia** (np. 70%): kolumna zdał/nie zdał w wynikach i komunikat dla uczestnika. | wysoka | niski |
| E3 | **Statystyki pytań:** % poprawnych odpowiedzi per pytanie i rozkład wyborów A/B/C/D. Pokazuje, czego ludzie nie zrozumieli na szkoleniu, i wyłapuje błędnie zaimportowane pytania (np. pytanie z 5% poprawnych to często zła litera w pliku). | wysoka | niski (dane już są w `arkusz_wynikow`) |
| E4 | **Kolumna `wyjasnienie` w pliku pytań**, pokazywana w podglądzie odpowiedzi („dlaczego B”). Zamienia test z egzaminu w narzędzie nauki. | wysoka | niski |
| E5 | **Podgląd na żywo podczas sesji:** ile osób wystartowało, jest w trakcie, skończyło (auto-odświeżanie co 10 s). Przydaje się, gdy test robi się na sali. | średnia | niski |
| E6 | **Przypomnienia mailem** do osób z niewykorzystanym albo nieukończonym tokenem (po F3). | średnia | niski |
| E7 | **Kod QR na ekranie** z linkiem do testu, do rzutnika na szkoleniu. Uczestnik skanuje i wpisuje token (albo dostaje QR z tokenem w mailu). Biblioteka `qrcode` albo generowanie SVG. | średnia | niski |
| E8 | **Kategorie pytań + losowanie proporcjonalne** (kolumna `kategoria` w pliku, np. „5 z Rezerwacji, 5 z Płatności”) i wynik per kategoria. | wysoka | średni |
| E9 | **Pre-test / post-test:** ta sama pula przed i po szkoleniu, raport przyrostu wiedzy per osoba i dla grupy. Mierzy skuteczność szkolenia. | wysoka | średni |
| E10 | **Edycja pytań w panelu** (poprawa literówki bez ponownego importu), podgląd całego banku, duplikowanie testu. | średnia | średni |
| E11 | **Retencja danych (RODO):** automatyczna anonimizacja imion i maili po N dniach od zamknięcia testu, z zachowaniem statystyk. | średnia | niski |
| E12 | **Log zdarzeń admina** (kto kiedy zresetował token, opublikował odpowiedzi). | niska | niski |

### Dla uczestnika

| ID | Propozycja | Wartość | Koszt |
|----|-----------|---------|-------|
| E13 | **Wznowienie testu** po przerwie albo na innym urządzeniu (wynika z L1). | wysoka | w cenie L1 |
| E14 | **Ekran startowy przed testem:** nazwa testu, liczba pytań, limit czasu, zasady (brak cofania, kiedy będą wyniki), przycisk „Rozpoczynam”. Czas rusza dopiero po kliknięciu. | wysoka | niski |
| E15 | **Wygodna obsługa:** duże kafelki odpowiedzi, klawisze 1–4, działanie na telefonie (UI1, UI5). | wysoka | niski |
| E16 | **Oznacz do powrotu i przejrzyj przed wysłaniem**, jako opcja testu (dziś przejście jest wyłącznie sekwencyjne). | średnia | średni |
| E17 | **Certyfikat / potwierdzenie ukończenia w PDF** przy zaliczeniu. | niska–średnia | średni |
| E18 | **Krótka ankieta po teście** (ocena szkolenia 1–5 + komentarz), widoczna dla trenera. | średnia | niski |
| E19 | **Inne typy pytań:** prawda/fałsz, wielokrotny wybór, pytanie z obrazkiem. | średnia | wysoki |

### Utrudnianie ściągania (miękkie)

Losowa kolejność opcji (L4), limit czasu (F1), brak cofania (jest), kontrolowana publikacja odpowiedzi (F2). Opcjonalnie informacyjny licznik przełączeń karty (`visibilitychange`) widoczny tylko dla admina, bez blokowania, bo to łatwo daje fałszywe alarmy.

---

## 7. Kolejność wdrażania

Każdy etap kończy się działającą aplikacją i może trafić na produkcję osobno.

### Etap 0: przygotowanie (0,5 dnia)
- S4: szkielet testów `pytest` + test obecnego przepływu (siatka bezpieczeństwa przed przebudową).
- S5: przypięcie wersji, `pip install` tylko przy tworzeniu `.venv`.
- UI2: `base.html` + przepięcie wszystkich szablonów (zmiana mechaniczna, ułatwia wszystko dalej).

### Etap 1: szybkie poprawki bezpieczeństwa i błędów (0,5–1 dzień)
- B2 open redirect, B4 debug na `127.0.0.1`, B3/S3 CSRF.
- B7 walidacja odpowiedzi, B10 PRG przy tokenach, B11 walidacja CLI, B12, B14, B15, B16, B18, B19, B20.
- B17 poprawki README.
- UI1 viewport, UI3 style linków, UI4 kategorie komunikatów.

### Etap 2: przebudowa przebiegu testu (1–2 dni) ← **najważniejszy etap**
- L1/S2: tabela `podejscia`, zapis każdej odpowiedzi od razu, usunięcie `flask_session/`.
- B8: `UNIQUE(token, pytanie_id)`.
- B1, B9, B13, E13 załatwione tym samym.
- L3: mianownik wyniku z `podejscia`.
- L2: reset / unieważnienie tokenu, statusy tokenów (UI8).

### Etap 3: import (0,5–1 dzień)
- S1: pandas → openpyxl (też szablon i eksporty).
- B5, B6, L5: walidacja z raportem błędów per wiersz, normalizacja nagłówków, podgląd przed zatwierdzeniem.
- E4: opcjonalna kolumna `wyjasnienie` (skoro i tak ruszamy import).

### Etap 4: kontrola nad testem (1–2 dni)
- Strona „Ustawienia testu” (edycja parametrów po imporcie).
- **F2:** tryb widoczności szczegółów + „Zamknij test i opublikuj”, okno `dostepny_od/do`.
- **F1:** limit czasu z licznikiem.
- E14: ekran startowy z zasadami.
- UI5, UI6, UI7: przebudowa strony pytania i wyniku.

### Etap 5: eksporty i raporty (0,5–1 dzień)
- E1/UI10: eksport wyników XLSX, UI9: kopiowanie/eksport tokenów.
- E2: próg zaliczenia.
- E3: statystyki pytań.
- S7: kopia bazy z panelu.

### Etap 6: maile (1 dzień + czas oczekiwania na IT)
- **Wcześniej, już przy etapie 0:** wysłać zapytanie do IT o skrzynkę SMTP / relay (patrz F3), żeby odpowiedź była gotowa na ten etap.
- L6: osobne pola `imie` / `email`, import listy z CSV/XLSX.
- **F3:** konfiguracja SMTP, szablon, wysyłka w tle, statusy. Albo plan B: `mailto:` + eksport CSV pod korespondencję seryjną.
- E6: przypomnienia.

### Etap 7+: rozwój (wg potrzeb)
E5 podgląd na żywo → E7 QR → E8 kategorie → E9 pre/post-test → E10 edycja pytań → E11 RODO → E18 ankieta → L4 losowanie opcji → E16 → E17 → E19.

**Łącznie etapy 0–6: ok. 5–8,5 dnia pracy przy ręcznym programowaniu.** To zgrubny szacunek oparty na rozmiarze zmian, nie na danych historycznych. Zakłada jedną osobę znającą Flaska, pełne dni pracy, kod + testy `pytest` + ręczne sprawdzenie. Nie obejmuje czekania na IT, próbnego testu z uczestnikami, review ani wdrożenia.

**Przy pracy z Claude Code** (według instrukcji z sekcji 0): ok. 5–8 h pracy agenta + ok. 5–7 h czasu usera na decyzje, review i ręczne testy, czyli realnie 2–3 dni kalendarzowe przy pracy częściowej.

---

## 8. Docelowe zmiany w schemacie bazy

Do dodania w istniejącym mechanizmie `_migruj_tabele` (`db.py:108`), czyli `ALTER TABLE ... ADD COLUMN` z wartościami domyślnymi, żeby istniejące bazy migrowały się same.

```sql
-- testy: ustawienia
ALTER TABLE testy ADD COLUMN limit_czasu_min INTEGER;              -- NULL = bez limitu (F1)
ALTER TABLE testy ADD COLUMN tryb_szczegolow TEXT NOT NULL DEFAULT 'natychmiast';  -- F2
ALTER TABLE testy ADD COLUMN szczegoly_od TEXT;                    -- F2, tryb od_daty / data awaryjna
ALTER TABLE testy ADD COLUMN wynik_widoczny TEXT NOT NULL DEFAULT 'od_razu';        -- F2
ALTER TABLE testy ADD COLUMN dostepny_od TEXT;                     -- F2 okno
ALTER TABLE testy ADD COLUMN dostepny_do TEXT;
ALTER TABLE testy ADD COLUMN zamkniety INTEGER NOT NULL DEFAULT 0; -- "Zamknij test i opublikuj"
ALTER TABLE testy ADD COLUMN prog_zaliczenia INTEGER;              -- E2, procent
ALTER TABLE testy ADD COLUMN mail_temat TEXT;                      -- F3
ALTER TABLE testy ADD COLUMN mail_tresc TEXT;

-- tokeny: dane osoby i status maila
ALTER TABLE tokeny ADD COLUMN imie TEXT;                           -- L6 (migracja z `przypisany`)
ALTER TABLE tokeny ADD COLUMN email TEXT;
ALTER TABLE tokeny ADD COLUMN mail_wyslany_at TEXT;                -- F3
ALTER TABLE tokeny ADD COLUMN mail_status TEXT;

-- pytania
ALTER TABLE pytania ADD COLUMN wyjasnienie TEXT;                   -- E4
ALTER TABLE pytania ADD COLUMN kategoria TEXT;                     -- E8

-- nowa tabela: przebieg podejścia (L1)
CREATE TABLE IF NOT EXISTS podejscia (
    token TEXT PRIMARY KEY REFERENCES tokeny(token),
    test_id INTEGER NOT NULL REFERENCES testy(id),
    pytania_json TEXT NOT NULL,        -- lista id wylosowanych pytań (+ ew. mapowanie opcji, L4)
    indeks INTEGER NOT NULL DEFAULT 0,
    rozpoczeto TEXT NOT NULL,
    termin TEXT,                       -- rozpoczeto + limit (F1), NULL = bez limitu
    zakonczono TEXT,
    status TEXT NOT NULL DEFAULT 'w_trakcie'   -- w_trakcie / ukonczony / czas_minal / uniewazniony
);

-- odpowiedzi: ochrona przed duplikatami (B8)
CREATE UNIQUE INDEX IF NOT EXISTS uq_odpowiedz ON odpowiedzi_uzytkownika(token, pytanie_id);
```

Uwaga: `CREATE UNIQUE INDEX` nie powiedzie się, jeśli w istniejącej bazie są już duplikaty (B8). Migracja musi je najpierw usunąć, zostawiając najstarszy wiersz.

Widoki `zbiorcze_wyniki` / `arkusz_wynikow` rozszerzyć o `test_id` (B16) i liczyć `wszystkie` z `podejscia.pytania_json` (L3).
