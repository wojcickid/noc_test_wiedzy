"""Wspólny dostęp do bazy SQLite używany przez aplikację i skrypty pomocnicze."""

import os
import secrets
import sqlite3
import string
from contextlib import contextmanager
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PLIK = os.path.join(BASE_DIR, "baza.db")

# Bez znaków łatwych do pomylenia przy przepisywaniu (0/O, 1/I/L) — używane
# zarówno do tokenów, jak i do generowanego hasła panelu administracyjnego.
ALFABET_KODOW = "".join(sorted(set(string.ascii_uppercase + string.digits) - set("0O1IL")))

WYMAGANE_KOLUMNY_PYTAN = ["tresc_pytania", "opcja_a", "opcja_b", "opcja_c", "opcja_d", "odpowiedz"]


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
    odpowiedz TEXT NOT NULL
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

CREATE INDEX IF NOT EXISTS idx_pytania_test ON pytania(test_id);
CREATE INDEX IF NOT EXISTS idx_tokeny_test ON tokeny(test_id);
CREATE INDEX IF NOT EXISTS idx_odpowiedzi_token ON odpowiedzi_uzytkownika(token);
"""

# Widoki są odtwarzane przy każdym starcie (DROP + CREATE, nie IF NOT EXISTS),
# żeby zmiany w ich definicji zawsze się zastosowały — nie trzymają danych,
# więc nie ma ryzyka utraty czegokolwiek.
SCHEMAT_WIDOKI = """
DROP VIEW IF EXISTS arkusz_wynikow;
-- Odpowiednik dawnego "arkusza wyników" (wyniki_<token>.xlsx) — pytanie po
-- pytaniu, z odpowiedzią użytkownika i poprawną odpowiedzią (litera + treść).
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
    ou.data_wyslania AS data_wyslania
FROM odpowiedzi_uzytkownika ou
JOIN pytania p ON p.id = ou.pytanie_id;

DROP VIEW IF EXISTS zbiorcze_wyniki;
-- Odpowiednik dawnego wyniki_testu.xlsx — jeden wiersz na uczestnika.
CREATE VIEW zbiorcze_wyniki AS
SELECT
    ou.token AS token,
    tk.przypisany AS przypisany,
    t.id AS test_id,
    t.nazwa AS test,
    COUNT(*) AS wszystkie,
    SUM(CASE WHEN ou.odpowiedz = p.odpowiedz THEN 1 ELSE 0 END) AS poprawne,
    ROUND(100.0 * SUM(CASE WHEN ou.odpowiedz = p.odpowiedz THEN 1 ELSE 0 END) / COUNT(*), 1) AS procent,
    MAX(ou.data_wyslania) AS data_wyslania
FROM odpowiedzi_uzytkownika ou
JOIN pytania p ON p.id = ou.pytanie_id
JOIN tokeny tk ON tk.token = ou.token
JOIN testy t ON t.id = tk.test_id
GROUP BY ou.token, t.id;
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


def importuj_test_z_dataframe(nazwa_testu, df, liczba_pytan=20):
    """Tworzy nowy test i wczytuje do niego pytania z pandas.DataFrame
    (kolumny: tresc_pytania, opcja_a..d, odpowiedz). `liczba_pytan` to ile
    pytań losować przy każdym podejściu — przycinane do liczby pytań w pliku.
    Zwraca (test_id, liczba_pytan_w_pliku, faktyczna_liczba_do_losowania)."""
    brakujace = [k for k in WYMAGANE_KOLUMNY_PYTAN if k not in df.columns]
    if brakujace:
        raise BladImportu(f"W pliku brakuje kolumn: {', '.join(brakujace)}")
    if len(df) == 0:
        raise BladImportu("Plik nie zawiera żadnych pytań.")

    liczba_pytan = max(1, min(int(liczba_pytan), len(df)))

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
            INSERT INTO pytania (test_id, tresc_pytania, opcja_a, opcja_b, opcja_c, opcja_d, odpowiedz)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    test_id,
                    str(wiersz["tresc_pytania"]),
                    str(wiersz["opcja_a"]),
                    str(wiersz["opcja_b"]),
                    str(wiersz["opcja_c"]),
                    str(wiersz["opcja_d"]),
                    str(wiersz["odpowiedz"]).strip().upper(),
                )
                for _, wiersz in df.iterrows()
            ],
        )

    return test_id, len(df), liczba_pytan


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
