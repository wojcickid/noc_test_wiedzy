"""Wspólny dostęp do bazy SQLite używany przez aplikację i skrypty pomocnicze."""

import io
import json
import os
import secrets
import sqlite3
import string
from contextlib import contextmanager
from datetime import datetime

import openpyxl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PLIK = os.path.join(BASE_DIR, "baza.db")

# Bez znaków łatwych do pomylenia przy przepisywaniu (0/O, 1/I/L) — używane
# zarówno do tokenów, jak i do generowanego hasła panelu administracyjnego.
ALFABET_KODOW = "".join(sorted(set(string.ascii_uppercase + string.digits) - set("0O1IL")))

WYMAGANE_KOLUMNY_PYTAN = ["tresc_pytania", "opcja_a", "opcja_b", "opcja_c", "opcja_d", "odpowiedz"]
# Opcjonalna — treść pokazywana przy wyniku uczestnika, wyjaśniająca poprawną
# odpowiedź (E4). Plik bez tej kolumny importuje się normalnie.
KOLUMNA_WYJASNIENIE = "wyjasnienie"
ODPOWIEDZI_DOZWOLONE = {"A", "B", "C", "D"}


class BladImportu(Exception):
    pass

SCHEMAT_TABELE = """
CREATE TABLE IF NOT EXISTS testy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nazwa TEXT NOT NULL UNIQUE,
    data_importu TEXT NOT NULL,
    liczba_pytan_do_losowania INTEGER NOT NULL DEFAULT 20
);

CREATE TABLE IF NOT EXISTS pytania (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL REFERENCES testy(id),
    tresc_pytania TEXT NOT NULL,
    opcja_a TEXT NOT NULL,
    opcja_b TEXT NOT NULL,
    opcja_c TEXT NOT NULL,
    opcja_d TEXT NOT NULL,
    odpowiedz TEXT NOT NULL,
    wyjasnienie TEXT
);

CREATE TABLE IF NOT EXISTS tokeny (
    token TEXT PRIMARY KEY,
    test_id INTEGER NOT NULL REFERENCES testy(id),
    wykorzystany INTEGER NOT NULL DEFAULT 0,
    data_utworzenia TEXT NOT NULL,
    data_wykorzystania TEXT,
    przypisany TEXT
);

CREATE TABLE IF NOT EXISTS odpowiedzi_uzytkownika (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL REFERENCES tokeny(token),
    pytanie_id INTEGER NOT NULL REFERENCES pytania(id),
    odpowiedz TEXT NOT NULL,
    data_wyslania TEXT NOT NULL
);

-- Postęp podejścia do testu (Etap 2, L1) — jedna aktywna/zakończona próba na
-- token. Każda odpowiedź trafia od razu do odpowiedzi_uzytkownika, więc utrata
-- ciasteczka/sesji przeglądarki nie kasuje postępu (B1, B13) i test można
-- wznowić tym samym tokenem na dowolnym urządzeniu (E13).
CREATE TABLE IF NOT EXISTS podejscia (
    token TEXT PRIMARY KEY REFERENCES tokeny(token),
    test_id INTEGER NOT NULL REFERENCES testy(id),
    wybrane_pytania TEXT NOT NULL,
    liczba_pytan INTEGER NOT NULL,
    indeks_pytania INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'w_trakcie',
    data_rozpoczecia TEXT NOT NULL,
    data_zakonczenia TEXT
);

CREATE INDEX IF NOT EXISTS idx_pytania_test ON pytania(test_id);
CREATE INDEX IF NOT EXISTS idx_tokeny_test ON tokeny(test_id);
CREATE INDEX IF NOT EXISTS idx_odpowiedzi_token ON odpowiedzi_uzytkownika(token);
CREATE INDEX IF NOT EXISTS idx_podejscia_test ON podejscia(test_id);
-- Jeden wiersz na parę (token, pytanie) — gwarantuje w SQLite, że dwa
-- równoczesne zapisy tej samej odpowiedzi się nie zduplikują (B8).
CREATE UNIQUE INDEX IF NOT EXISTS idx_odpowiedzi_unikalne ON odpowiedzi_uzytkownika(token, pytanie_id);
"""

# Widoki są odtwarzane przy każdym starcie (DROP + CREATE, nie IF NOT EXISTS),
# żeby zmiany w ich definicji zawsze się zastosowały — nie trzymają danych,
# więc nie ma ryzyka utraty czegokolwiek.
SCHEMAT_WIDOKI = """
DROP VIEW IF EXISTS arkusz_wynikow;
-- Odpowiednik dawnego "arkusza wyników" (wyniki_<token>.xlsx) — pytanie po
-- pytaniu, z odpowiedzią użytkownika i poprawną odpowiedzią (litera + treść).
-- Tylko podejścia zakończone (L1) — w trakcie trwania testu nie pokazujemy
-- cząstkowych wyników nikomu, kto poda/sprawdzi ten sam token po drodze.
CREATE VIEW arkusz_wynikow AS
SELECT
    ou.token AS token,
    p.tresc_pytania AS tresc_pytania,
    ou.odpowiedz AS odpowiedz_uzytkownika,
    CASE ou.odpowiedz
        WHEN 'A' THEN p.opcja_a WHEN 'B' THEN p.opcja_b
        WHEN 'C' THEN p.opcja_c WHEN 'D' THEN p.opcja_d
    END AS tresc_odpowiedzi_uzytkownika,
    p.odpowiedz AS poprawna_odpowiedz,
    CASE p.odpowiedz
        WHEN 'A' THEN p.opcja_a WHEN 'B' THEN p.opcja_b
        WHEN 'C' THEN p.opcja_c WHEN 'D' THEN p.opcja_d
    END AS tresc_poprawnej_odpowiedzi,
    p.wyjasnienie AS wyjasnienie,
    ou.data_wyslania AS data_wyslania
FROM odpowiedzi_uzytkownika ou
JOIN pytania p ON p.id = ou.pytanie_id
JOIN podejscia pj ON pj.token = ou.token
WHERE pj.status = 'zakonczone';

DROP VIEW IF EXISTS zbiorcze_wyniki;
-- Odpowiednik dawnego wyniki_testu.xlsx — jeden wiersz na zakończone podejście.
-- Mianownik (wszystkie) to liczba wylosowanych pytań z podejscia, nie COUNT()
-- udzielonych odpowiedzi (L3) — te dwie liczby są równe dla normalnie
-- ukończonego podejścia, ale tylko ta pierwsza jest poprawna, gdyby kiedyś
-- się rozjechały (np. ręczna ingerencja w dane).
CREATE VIEW zbiorcze_wyniki AS
SELECT
    pj.token AS token,
    tk.przypisany AS przypisany,
    t.id AS test_id,
    t.nazwa AS test,
    pj.liczba_pytan AS wszystkie,
    (
        SELECT COUNT(*) FROM odpowiedzi_uzytkownika ou
        JOIN pytania p ON p.id = ou.pytanie_id
        WHERE ou.token = pj.token AND ou.odpowiedz = p.odpowiedz
    ) AS poprawne,
    ROUND(
        100.0 * (
            SELECT COUNT(*) FROM odpowiedzi_uzytkownika ou
            JOIN pytania p ON p.id = ou.pytanie_id
            WHERE ou.token = pj.token AND ou.odpowiedz = p.odpowiedz
        ) / pj.liczba_pytan, 1
    ) AS procent,
    pj.data_zakonczenia AS data_wyslania
FROM podejscia pj
JOIN tokeny tk ON tk.token = pj.token
JOIN testy t ON t.id = tk.test_id
WHERE pj.status = 'zakonczone';
"""


def _migruj_tabele(conn):
    """Dodaje kolumny do już istniejących baz, jeśli schemat ewoluował od czasu
    ich utworzenia — tabele (w przeciwieństwie do widoków) trzymają dane, więc
    nie można ich po prostu odtworzyć od nowa."""
    kolumny_tokeny = {w["name"] for w in conn.execute("PRAGMA table_info(tokeny)").fetchall()}
    if "przypisany" not in kolumny_tokeny:
        conn.execute("ALTER TABLE tokeny ADD COLUMN przypisany TEXT")

    kolumny_testy = {w["name"] for w in conn.execute("PRAGMA table_info(testy)").fetchall()}
    if "liczba_pytan_do_losowania" not in kolumny_testy:
        conn.execute("ALTER TABLE testy ADD COLUMN liczba_pytan_do_losowania INTEGER NOT NULL DEFAULT 20")

    kolumny_pytania = {w["name"] for w in conn.execute("PRAGMA table_info(pytania)").fetchall()}
    if "wyjasnienie" not in kolumny_pytania:
        conn.execute("ALTER TABLE pytania ADD COLUMN wyjasnienie TEXT")

    _odtworz_historyczne_podejscia(conn)


def _odtworz_historyczne_podejscia(conn):
    """Etap 2 (L1) wprowadził tabelę `podejscia` — starsze odpowiedzi zapisane
    jeszcze w modelu "wszystko naraz w /wynik" nie mają dla siebie wiersza w tej
    tabeli. Bez tego zniknęłyby z widoków wyników (które teraz wymagają
    podejscia.status='zakonczone'), więc odtwarzamy brakujące wiersze jako
    zakończone podejścia na podstawie istniejących odpowiedzi. Idempotentne —
    po pierwszym uruchomieniu każdy taki token ma już swój wiersz."""
    brakujace_podejscia = conn.execute(
        """
        SELECT DISTINCT ou.token AS token, tk.test_id AS test_id
        FROM odpowiedzi_uzytkownika ou
        JOIN tokeny tk ON tk.token = ou.token
        LEFT JOIN podejscia pj ON pj.token = ou.token
        WHERE pj.token IS NULL
        """
    ).fetchall()
    for wiersz in brakujace_podejscia:
        pytania_id = [
            w["pytanie_id"]
            for w in conn.execute(
                "SELECT pytanie_id FROM odpowiedzi_uzytkownika WHERE token = ? ORDER BY id",
                (wiersz["token"],),
            ).fetchall()
        ]
        czasy = conn.execute(
            "SELECT MIN(data_wyslania) AS start, MAX(data_wyslania) AS koniec "
            "FROM odpowiedzi_uzytkownika WHERE token = ?",
            (wiersz["token"],),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO podejscia
                (token, test_id, wybrane_pytania, liczba_pytan, indeks_pytania, status, data_rozpoczecia, data_zakonczenia)
            VALUES (?, ?, ?, ?, ?, 'zakonczone', ?, ?)
            """,
            (
                wiersz["token"],
                wiersz["test_id"],
                json.dumps(pytania_id),
                len(pytania_id),
                len(pytania_id),
                czasy["start"],
                czasy["koniec"],
            ),
        )


def polacz():
    conn = sqlite3.connect(DB_PLIK, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def inicjalizuj():
    with polacz() as conn:
        conn.executescript(SCHEMAT_TABELE)
        _migruj_tabele(conn)
        conn.executescript(SCHEMAT_WIDOKI)
        conn.commit()
    conn.close()


@contextmanager
def baza():
    """Kontekst: otwiera połączenie, commituje po udanym bloku, zawsze zamyka."""
    conn = polacz()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def losowy_kod(dlugosc=8):
    return "".join(secrets.choice(ALFABET_KODOW) for _ in range(dlugosc))


def _komorka_na_tekst(wartosc):
    """Zamienia wartość komórki openpyxl na tekst: pusta komórka (`None`) daje
    `""` zamiast napisu `"nan"`, a liczba całkowita zapisana jako float (np.
    `5.0`, bo kolumna miała gdzieś pustą komórkę) traci zbędne `.0` (B5)."""
    if wartosc is None:
        return ""
    if isinstance(wartosc, float) and wartosc.is_integer():
        return str(int(wartosc))
    return str(wartosc).strip()


def wczytaj_i_zwaliduj_plik_pytan(dane_pliku):
    """Parsuje plik .xlsx z pytaniami i waliduje go wiersz po wierszu (B6).
    Nagłówki są normalizowane (`strip().lower()`), więc `Tresc_pytania` albo
    spacja na końcu nazwy kolumny nie psują importu. Puste wiersze (np. odstęp
    na końcu arkusza) są pomijane bez błędu. Zwraca `(pytania, bledy)` —
    `pytania` to lista słowników gotowych do zapisu (do podglądu przed
    zatwierdzeniem, L5), `bledy` to lista czytelnych komunikatów, po jednym na
    problem. Niepusta lista `bledy` oznacza, że pliku nie da się zaimportować
    w całości — cały plik jest wtedy odrzucany (decyzja z Etapu 3)."""
    try:
        skoroszyt = openpyxl.load_workbook(filename=io.BytesIO(dane_pliku), read_only=True, data_only=True)
    except Exception:
        return [], ["Nie udało się odczytać pliku — sprawdź, czy to poprawny plik .xlsx."]

    arkusz = skoroszyt.active
    wiersze = arkusz.iter_rows(values_only=True)
    try:
        naglowki_surowe = next(wiersze)
    except StopIteration:
        return [], ["Plik jest pusty."]

    naglowki = [(str(h).strip().lower() if h is not None else "") for h in naglowki_surowe]
    brakujace = [k for k in WYMAGANE_KOLUMNY_PYTAN if k not in naglowki]
    if brakujace:
        return [], [f"W pliku brakuje kolumn: {', '.join(brakujace)}"]

    indeksy = {nazwa: naglowki.index(nazwa) for nazwa in WYMAGANE_KOLUMNY_PYTAN}
    indeks_wyjasnienia = naglowki.index(KOLUMNA_WYJASNIENIE) if KOLUMNA_WYJASNIENIE in naglowki else None

    pytania = []
    bledy = []
    for numer_wiersza, wiersz in enumerate(wiersze, start=2):
        if wiersz is None or all(komorka is None for komorka in wiersz):
            continue

        wartosci = {
            nazwa: (_komorka_na_tekst(wiersz[idx]) if idx < len(wiersz) else "")
            for nazwa, idx in indeksy.items()
        }
        for nazwa in WYMAGANE_KOLUMNY_PYTAN:
            if not wartosci[nazwa]:
                bledy.append(f"wiersz {numer_wiersza}: puste pole '{nazwa}'")

        odpowiedz = wartosci["odpowiedz"].strip().upper()
        if wartosci["odpowiedz"] and odpowiedz not in ODPOWIEDZI_DOZWOLONE:
            bledy.append(
                f"wiersz {numer_wiersza}: nieprawidłowa odpowiedź '{wartosci['odpowiedz']}' (dozwolone: A, B, C, D)"
            )

        wyjasnienie = None
        if indeks_wyjasnienia is not None and indeks_wyjasnienia < len(wiersz):
            wyjasnienie = _komorka_na_tekst(wiersz[indeks_wyjasnienia]) or None

        pytania.append(
            {
                "tresc_pytania": wartosci["tresc_pytania"],
                "opcja_a": wartosci["opcja_a"],
                "opcja_b": wartosci["opcja_b"],
                "opcja_c": wartosci["opcja_c"],
                "opcja_d": wartosci["opcja_d"],
                "odpowiedz": odpowiedz,
                "wyjasnienie": wyjasnienie,
            }
        )

    if not pytania and not bledy:
        bledy.append("Plik nie zawiera żadnych pytań.")

    return pytania, bledy


def importuj_pytania(nazwa_testu, pytania, liczba_pytan=20):
    """Tworzy nowy test i wczytuje do niego już zwalidowane pytania (patrz
    `wczytaj_i_zwaliduj_plik_pytan`). `liczba_pytan` to ile pytań losować przy
    każdym podejściu — przycinane do liczby pytań w pliku. Zwraca
    (test_id, liczba_pytan_w_pliku, faktyczna_liczba_do_losowania)."""
    if not pytania:
        raise BladImportu("Plik nie zawiera żadnych pytań.")

    liczba_pytan = max(1, min(int(liczba_pytan), len(pytania)))

    with baza() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO testy (nazwa, data_importu, liczba_pytan_do_losowania) VALUES (?, ?, ?)",
                (nazwa_testu, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), liczba_pytan),
            )
        except sqlite3.IntegrityError:
            raise BladImportu(f"Test o nazwie '{nazwa_testu}' już istnieje. Wybierz inną nazwę.")
        test_id = cur.lastrowid

        conn.executemany(
            """
            INSERT INTO pytania (test_id, tresc_pytania, opcja_a, opcja_b, opcja_c, opcja_d, odpowiedz, wyjasnienie)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    test_id,
                    p["tresc_pytania"], p["opcja_a"], p["opcja_b"], p["opcja_c"], p["opcja_d"],
                    p["odpowiedz"], p.get("wyjasnienie"),
                )
                for p in pytania
            ],
        )

    return test_id, len(pytania), liczba_pytan


def wygeneruj_tokeny(test_id, liczba, dlugosc=8, przypisania=None):
    """Generuje `liczba` nowych, unikalnych tokenów dla wskazanego testu.
    Jeśli podano `przypisania` (lista imion/maili o długości `liczba`), i-ty
    token dostaje i-te przypisanie. Zwraca listę {"token", "przypisany"}."""
    if dlugosc < 4 or dlugosc > 20:
        raise ValueError("Długość tokenu musi być od 4 do 20 znaków.")
    if przypisania is not None and len(przypisania) != liczba:
        raise ValueError("Liczba przypisań musi odpowiadać liczbie tokenów.")

    # Limit prób, żeby żądanie liczby tokenów przekraczającej pulę możliwych
    # kodów (np. dlugosc=1 i liczba=40) kończyło się czytelnym błędem zamiast
    # zawieszenia aplikacji w nieskończonej pętli (B11).
    maks_prob = max(1000, liczba * 50)

    with baza() as conn:
        istniejace = {w["token"] for w in conn.execute("SELECT token FROM tokeny").fetchall()}
        nowe = []
        proba = 0
        while len(nowe) < liczba:
            if proba >= maks_prob:
                raise ValueError(
                    f"Nie udało się wygenerować {liczba} unikalnych tokenów o długości {dlugosc} — "
                    "zbyt mała pula możliwych kodów dla tej długości. Zwiększ długość tokenu."
                )
            proba += 1
            token = losowy_kod(dlugosc)
            if token not in istniejace and token not in nowe:
                nowe.append(token)

        teraz = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.executemany(
            "INSERT INTO tokeny (token, test_id, wykorzystany, data_utworzenia, przypisany) VALUES (?, ?, 0, ?, ?)",
            [(token, test_id, teraz, (przypisania[i] if przypisania else None)) for i, token in enumerate(nowe)],
        )
    return [{"token": token, "przypisany": (przypisania[i] if przypisania else None)} for i, token in enumerate(nowe)]


def przypisz_token(token, przypisany):
    """Ustawia/aktualizuje osobę przypisaną do tokenu. Zwraca True, jeśli token istniał."""
    with baza() as conn:
        cur = conn.execute("UPDATE tokeny SET przypisany = ? WHERE token = ?", (przypisany or None, token))
    return cur.rowcount > 0


def resetuj_token(token):
    """Akcja admina (L2) — kasuje podejście i dotychczasowe odpowiedzi powiązane
    z tokenem i odblokowuje go, żeby uczestnik mógł zacząć test od nowa.
    Zgodnie z decyzją z Etapu 2: reset usuwa poprzednie odpowiedzi (nie
    archiwizuje ich jako osobne podejście). Zwraca True, jeśli token istniał."""
    with baza() as conn:
        token_wiersz = conn.execute("SELECT 1 FROM tokeny WHERE token = ?", (token,)).fetchone()
        if token_wiersz is None:
            return False
        conn.execute("DELETE FROM odpowiedzi_uzytkownika WHERE token = ?", (token,))
        conn.execute("DELETE FROM podejscia WHERE token = ?", (token,))
        conn.execute(
            "UPDATE tokeny SET wykorzystany = 0, data_wykorzystania = NULL WHERE token = ?",
            (token,),
        )
    return True
