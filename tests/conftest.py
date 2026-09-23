"""Wspólne fixture'y pytest — izolowana baza SQLite dla każdego testu.

Uwaga: `test_wiedzy_app` przy imporcie modułu wczytuje/tworzy prawdziwe pliki projektu
`.flask_secret_key` i `.admin_haslo` (S4, Etap 0 — znane ograniczenie, patrz sekcja 0.5
w PLAN_POPRAWEK.md). Sama baza danych jest w pełni izolowana per test.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import test_wiedzy_app as app_module

# Mały bank pytań testowych — wszystkie odpowiedzi to "B", żeby łatwo liczyć wynik.
PYTANIA_TESTOWE = [
    {"tresc_pytania": "1+1=?", "opcja_a": "1", "opcja_b": "2", "opcja_c": "3", "opcja_d": "4", "odpowiedz": "B"},
    {"tresc_pytania": "2+2=?", "opcja_a": "3", "opcja_b": "4", "opcja_c": "5", "opcja_d": "6", "odpowiedz": "B"},
    {"tresc_pytania": "3+3=?", "opcja_a": "5", "opcja_b": "6", "opcja_c": "7", "opcja_d": "8", "odpowiedz": "B"},
]


@pytest.fixture
def klient(tmp_path, monkeypatch):
    """Klient testowy Flaska z izolowaną, tymczasową bazą SQLite."""
    monkeypatch.setattr(db, "DB_PLIK", str(tmp_path / "test.db"))
    db.inicjalizuj()

    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def haslo_admina():
    """Prawdziwe hasło panelu administracyjnego (wygenerowane przy imporcie modułu)."""
    return app_module.ADMIN_HASLO


@pytest.fixture
def test_z_pytaniami(klient):
    """Tworzy test z 3 pytaniami testowymi (liczba_pytan=3) i zwraca jego id."""
    test_id, _, _ = db.importuj_pytania("Test testowy", PYTANIA_TESTOWE.copy(), liczba_pytan=3)
    return test_id


def zaloguj_admina(klient, haslo_admina):
    return klient.post("/admin/login", data={"haslo": haslo_admina}, follow_redirects=True)


def pobierz_csrf_token(klient):
    """Token CSRF z bieżącej sesji klienta testowego — dostępny dopiero po wejściu na
    stronę panelu, bo to render szablonu (wywołanie csrf_token()) go tworzy."""
    with klient.session_transaction() as sess:
        return sess["csrf_token"]
