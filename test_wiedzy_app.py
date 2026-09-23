import base64
import binascii
import io
import json
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

import openpyxl
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for

from db import (
    BladImportu,
    FORMAT_DATY,
    TOLERANCJA_SEKUNDY,
    TRYBY_SZCZEGOLOW,
    TRYBY_WYNIKU,
    baza,
    domknij_przeterminowane_podejscia,
    importuj_pytania,
    inicjalizuj,
    losowy_kod,
    oblicz_termin,
    przypisz_token,
    resetuj_token,
    ustaw_zamkniecie_testu,
    wczytaj_i_zwaliduj_plik_pytan,
    wygeneruj_tokeny,
    zapisz_ustawienia_testu,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY_FILE = os.path.join(BASE_DIR, ".flask_secret_key")
ADMIN_HASLO_FILE = os.path.join(BASE_DIR, ".admin_haslo")

# Przykładowy zestaw pytań do jednoklikowego wgrania w panelu (/admin/import/przyklad)
PRZYKLADOWE_PYTANIA = [
    {"tresc_pytania": "Jaka jest stolica Polski?", "opcja_a": "Kraków", "opcja_b": "Warszawa",
     "opcja_c": "Wrocław", "opcja_d": "Poznań", "odpowiedz": "B",
     "wyjasnienie": "Warszawa jest stolicą Polski od 1596 roku."},
    {"tresc_pytania": "Ile kontynentów liczy Ziemia?", "opcja_a": "5", "opcja_b": "6",
     "opcja_c": "7", "opcja_d": "8", "odpowiedz": "C",
     "wyjasnienie": "Powszechnie przyjmuje się podział na 7 kontynentów."},
    {"tresc_pytania": "Ile wynosi liczba Pi w przybliżeniu do dwóch miejsc po przecinku?",
     "opcja_a": "3,12", "opcja_b": "3,14", "opcja_c": "3,16", "opcja_d": "3,18", "odpowiedz": "B",
     "wyjasnienie": "Liczba Pi to w przybliżeniu 3,14159…"},
    {"tresc_pytania": "W którym roku zakończyła się II wojna światowa?", "opcja_a": "1943",
     "opcja_b": "1944", "opcja_c": "1945", "opcja_d": "1946", "odpowiedz": "C",
     "wyjasnienie": "II wojna światowa zakończyła się w 1945 roku."},
    {"tresc_pytania": "Jaki gaz jest najbardziej rozpowszechniony w atmosferze Ziemi?",
     "opcja_a": "Tlen", "opcja_b": "Azot", "opcja_c": "Dwutlenek węgla", "opcja_d": "Wodór", "odpowiedz": "B",
     "wyjasnienie": "Azot stanowi ok. 78% atmosfery ziemskiej."},
]


def wczytaj_lub_utworz_sekret():
    """Trwały klucz sesji — inaczej każdy restart/reload procesu (np. w trybie debug)
    unieważniałby ciasteczka sesji wszystkich uczestników w trakcie testu."""
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, "rb") as f:
            klucz = f.read()
        if klucz:
            return klucz
    klucz = os.urandom(24)
    with open(SECRET_KEY_FILE, "wb") as f:
        f.write(klucz)
    return klucz


def wczytaj_lub_utworz_haslo_admina():
    """Hasło do panelu /admin — przy pierwszym uruchomieniu losowane i zapisywane
    do pliku, żeby nie trzeba było go ustawiać ręcznie przed pierwszym użyciem."""
    if os.path.exists(ADMIN_HASLO_FILE):
        with open(ADMIN_HASLO_FILE, "r", encoding="utf-8") as f:
            haslo = f.read().strip()
        if haslo:
            return haslo
    haslo = losowy_kod(10)
    with open(ADMIN_HASLO_FILE, "w", encoding="utf-8") as f:
        f.write(haslo)
    print(f"[panel administracyjny] Wygenerowano hasło administratora: {haslo}")
    print(f"[panel administracyjny] Zapisane w pliku {ADMIN_HASLO_FILE} — zmień je edytując ten plik.")
    return haslo


app = Flask(__name__)
app.secret_key = wczytaj_lub_utworz_sekret()
ADMIN_HASLO = wczytaj_lub_utworz_haslo_admina()

inicjalizuj()


def wymaga_admina(f):
    @wraps(f)
    def opakowana(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", nastepny=request.path))
        return f(*args, **kwargs)

    return opakowana


def bezpieczna_sciezka_powrotu(sciezka):
    """Akceptuje wyłącznie względne ścieżki wewnątrz aplikacji (zaczynające się
    od pojedynczego '/'), żeby ?nastepny=https://obca-strona nie wyprowadzał
    zalogowanego admina poza appkę (B2 — open redirect)."""
    if sciezka and sciezka.startswith("/") and not sciezka.startswith("//"):
        return sciezka
    return None


def generuj_csrf_token():
    """Token CSRF trzymany w sesji admina — jedno pole ukryte w każdym formularzu
    POST panelu, sprawdzane przez @csrf_chroniony (B3/S3)."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def csrf_chroniony(f):
    @wraps(f)
    def opakowana(*args, **kwargs):
        if request.method == "POST":
            token = request.form.get("csrf_token", "")
            if not token or not secrets.compare_digest(token, session.get("csrf_token", "")):
                abort(400, description="Nieprawidłowy lub wygasły token CSRF — odśwież stronę i spróbuj ponownie.")
        return f(*args, **kwargs)

    return opakowana


def okno_dostepnosci_ok(test, teraz):
    """Sprawdza okno dostępności testu (F2, punkt 5) — `dostepny_od`/`dostepny_do`
    dotyczą wyłącznie startu nowego podejścia, nie trwającego już testu."""
    if test["dostepny_od"] and teraz < datetime.strptime(test["dostepny_od"], FORMAT_DATY):
        return False, f"Ten test będzie dostępny od {sformatuj_date_pl(test['dostepny_od'])}."
    if test["dostepny_do"] and teraz > datetime.strptime(test["dostepny_do"], FORMAT_DATY):
        return False, "Termin na rozpoczęcie tego testu już minął."
    return True, None


def sformatuj_date_pl(wartosc):
    """Format daty do wyświetlania uczestnikom/adminowi (Etap 4, decyzja o
    formacie DD.MM.RRRR GG:MM, strefa Europe/Warsaw — czas serwera)."""
    if not wartosc:
        return ""
    try:
        return datetime.strptime(wartosc, FORMAT_DATY).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return wartosc


def rozpocznij_lub_wznow_podejscie(token):
    """Zwraca id testu, do którego token daje dostęp — jeśli można rozpocząć
    nowe podejście albo wznowić trwające (B1, E13) — albo None, jeśli token
    nie istnieje, podejście jest już zakończone/unieważnione, albo (dla
    nowego podejścia) test jest zamknięty lub poza oknem dostępności (F2).

    Pierwsze wejście atomowo oznacza token jako wykorzystany i losuje pytania
    podejścia (UPDATE...WHERE wykorzystany=0, jak dawniej w
    waliduj_i_zuzyj_token) — gwarantuje to w SQLite, że dwa równoczesne
    wejścia tym samym tokenem (podwójne kliknięcie „Rozpocznij”, B9) nie
    wylosują dwóch różnych zestawów pytań: przegrany wyścig po prostu
    dołącza do podejścia utworzonego przez zwycięzcę.

    Zegar (F1) startuje dopiero tutaj — czyli dopiero po kliknięciu
    „Rozpoczynam” na ekranie startowym (E14), nie przy samym wpisaniu tokenu."""
    with baza() as conn:
        token_wiersz = conn.execute(
            """
            SELECT tk.test_id AS test_id, t.zamkniety AS zamkniety,
                   t.dostepny_od AS dostepny_od, t.dostepny_do AS dostepny_do,
                   t.liczba_pytan_do_losowania AS liczba_pytan_do_losowania
            FROM tokeny tk JOIN testy t ON t.id = tk.test_id
            WHERE tk.token = ?
            """,
            (token,),
        ).fetchone()
        if token_wiersz is None:
            return None
        test_id = token_wiersz["test_id"]

        podejscie = conn.execute("SELECT status FROM podejscia WHERE token = ?", (token,)).fetchone()
        if podejscie is not None:
            return test_id if podejscie["status"] == "w_trakcie" else None

        if token_wiersz["zamkniety"]:
            return None
        ok, _ = okno_dostepnosci_ok(token_wiersz, datetime.now())
        if not ok:
            return None

        teraz = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            "UPDATE tokeny SET wykorzystany = 1, data_wykorzystania = ? WHERE token = ? AND wykorzystany = 0",
            (teraz, token),
        )
        if cur.rowcount != 1:
            podejscie = conn.execute("SELECT status FROM podejscia WHERE token = ?", (token,)).fetchone()
            return test_id if podejscie is not None and podejscie["status"] == "w_trakcie" else None

        liczba_pytan = token_wiersz["liczba_pytan_do_losowania"] or 20
        wiersze = conn.execute(
            "SELECT id FROM pytania WHERE test_id = ? ORDER BY RANDOM() LIMIT ?",
            (test_id, liczba_pytan),
        ).fetchall()
        wybrane_pytania_id = [w["id"] for w in wiersze]

        conn.execute(
            """
            INSERT INTO podejscia (token, test_id, wybrane_pytania, liczba_pytan, indeks_pytania, status, data_rozpoczecia)
            VALUES (?, ?, ?, ?, 0, 'w_trakcie', ?)
            """,
            (token, test_id, json.dumps(wybrane_pytania_id), len(wybrane_pytania_id), teraz),
        )
    return test_id


def waliduj_token_startu(token):
    """Sprawdzenie tokenu na stronie głównej (bez efektów ubocznych) — token
    musi istnieć; jeśli podejście już trwa, wznowienie jest zawsze możliwe;
    jeśli podejście jeszcze nie istnieje, test nie może być zamknięty ani poza
    oknem dostępności (F2). Zwraca (test_id, None) albo (None, komunikat)."""
    with baza() as conn:
        wiersz = conn.execute(
            """
            SELECT tk.test_id AS test_id, t.zamkniety AS zamkniety,
                   t.dostepny_od AS dostepny_od, t.dostepny_do AS dostepny_do
            FROM tokeny tk JOIN testy t ON t.id = tk.test_id
            WHERE tk.token = ?
            """,
            (token,),
        ).fetchone()
        if wiersz is None:
            return None, "Nieprawidłowy token dostępu."

        podejscie = conn.execute("SELECT status FROM podejscia WHERE token = ?", (token,)).fetchone()
        if podejscie is not None:
            if podejscie["status"] == "w_trakcie":
                return wiersz["test_id"], None
            return None, "Ten token został już wykorzystany."

        if wiersz["zamkniety"]:
            return None, "Ten test został zamknięty przez prowadzącego."
        ok, komunikat = okno_dostepnosci_ok(wiersz, datetime.now())
        if not ok:
            return None, komunikat

    return wiersz["test_id"], None


def szczegoly_dostepne(test, teraz):
    """Czy uczestnik może teraz zobaczyć szczegółowe odpowiedzi (F2)."""
    tryb = test["tryb_szczegolow"]
    if tryb == "natychmiast":
        return True, None
    if tryb == "po_zamknieciu":
        if test["zamkniety"]:
            return True, None
        return False, "Szczegółowe odpowiedzi będą dostępne po zakończeniu testu przez prowadzącego."
    if tryb == "od_daty":
        if test["szczegoly_od"] and teraz >= datetime.strptime(test["szczegoly_od"], FORMAT_DATY):
            return True, None
        if test["szczegoly_od"]:
            return False, f"Szczegółowe odpowiedzi będą dostępne od {sformatuj_date_pl(test['szczegoly_od'])}."
        return False, "Szczegółowe odpowiedzi nie są jeszcze dostępne."
    return False, "Szczegółowe odpowiedzi są dostępne tylko dla prowadzącego."


def wynik_dostepny(test, teraz):
    """Czy uczestnik może teraz zobaczyć wynik punktowy (F2) — w trybie
    „razem ze szczegółami” korzysta z tej samej reguły co szczegoly_dostepne."""
    if test["wynik_widoczny"] == "od_razu":
        return True, None
    return szczegoly_dostepne(test, teraz)


def _zamknij_podejscie_z_powodu_czasu(conn, token):
    teraz_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE podejscia SET status = 'czas_minal', data_zakonczenia = ? WHERE token = ? AND status = 'w_trakcie'",
        (teraz_str, token),
    )


def sprawdz_i_domknij_jesli_czas_minal(conn, token, podejscie, test):
    """Sprawdza limit czasu (+ tolerancja) dla pojedynczego podejścia w_trakcie
    w ramach już otwartego połączenia — używane w /test i /wynik, żeby
    odpowiedź spóźniona ponad tolerancję nigdy nie została zapisana (F1)."""
    if test["limit_czasu_min"] is None:
        return False
    termin = oblicz_termin(podejscie["data_rozpoczecia"], test["limit_czasu_min"]) + timedelta(seconds=TOLERANCJA_SEKUNDY)
    if datetime.now() <= termin:
        return False
    _zamknij_podejscie_z_powodu_czasu(conn, token)
    return True


app.jinja_env.globals["csrf_token"] = generuj_csrf_token
app.jinja_env.filters["data_pl"] = sformatuj_date_pl


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        token = (request.form.get("token") or "").strip().upper()
        if not token:
            flash("Podaj token dostępu.", "blad")
            return redirect(url_for("index"))

        test_id, blad = waliduj_token_startu(token)
        if test_id is None:
            flash(blad or "Nieprawidłowy lub już wykorzystany token dostępu.", "blad")
            return redirect(url_for("index"))

        # W sesji (ciasteczku) trzymamy wyłącznie sam token — postęp i pytania
        # są w bazie (L1), więc ten sam token wznawia test na dowolnym
        # urządzeniu, wystarczy go ponownie wpisać na stronie głównej (E13).
        # Sam wpisanie tokenu jeszcze NIE uruchamia zegara (E14) — to robi
        # dopiero kliknięcie „Rozpoczynam” na ekranie startowym w /test.
        session["token"] = token
        return redirect(url_for("test"))
    return render_template("index.html")


@app.route("/test", methods=["GET", "POST"])
def test():
    token = session.get("token")
    if not token:
        return redirect(url_for("index"))

    with baza() as conn:
        test_wiersz = conn.execute(
            "SELECT t.* FROM tokeny tk JOIN testy t ON t.id = tk.test_id WHERE tk.token = ?", (token,)
        ).fetchone()
        if test_wiersz is None:
            session.pop("token", None)
            return redirect(url_for("index"))
        test_dict = dict(test_wiersz)
        podejscie = conn.execute("SELECT * FROM podejscia WHERE token = ?", (token,)).fetchone()

    if request.method == "POST" and request.form.get("start"):
        nowy_test_id = rozpocznij_lub_wznow_podejscie(token)
        if nowy_test_id is None:
            flash("Nie udało się rozpocząć testu — token jest nieprawidłowy, już wykorzystany albo test jest niedostępny.", "blad")
            session.pop("token", None)
            return redirect(url_for("index"))
        return redirect(url_for("test"))

    if podejscie is None:
        # Ekran startowy (E14) — zegar limitu czasu (F1) startuje dopiero po
        # kliknięciu „Rozpoczynam” (obsłużone wyżej), nie przy samym wejściu tu.
        if test_dict["zamkniety"]:
            session.pop("token", None)
            flash("Ten test został zamknięty przez prowadzącego.", "blad")
            return redirect(url_for("index"))
        ok, komunikat = okno_dostepnosci_ok(test_dict, datetime.now())
        if not ok:
            session.pop("token", None)
            flash(komunikat, "blad")
            return redirect(url_for("index"))
        return render_template("start.html", test=test_dict)

    if podejscie["status"] != "w_trakcie":
        return redirect(url_for("wynik"))

    with baza() as conn:
        if sprawdz_i_domknij_jesli_czas_minal(conn, token, podejscie, test_dict):
            return redirect(url_for("wynik"))

    wybrane_pytania_id = json.loads(podejscie["wybrane_pytania"])
    if not wybrane_pytania_id:
        # Test bez pytań (B12) — bez tego GET /test i GET /wynik przekierowują
        # do siebie nawzajem w nieskończoność.
        session.pop("token", None)
        flash("Ten test nie ma jeszcze żadnych pytań. Skontaktuj się z organizatorem.", "blad")
        return redirect(url_for("index"))

    indeks = podejscie["indeks_pytania"]

    if request.method == "POST":
        pytanie_id = request.form.get("pytanie_id")
        odpowiedz = request.form.get("odpowiedz")
        oczekiwane_id = wybrane_pytania_id[indeks] if indeks < len(wybrane_pytania_id) else None

        if pytanie_id is None or not pytanie_id.isdigit() or int(pytanie_id) != oczekiwane_id:
            # Niezgodność pytanie_id (np. cofnięcie w przeglądarce po udzieleniu
            # odpowiedzi) to nie to samo co brak zaznaczenia — osobny komunikat (B14).
            flash("To pytanie zostało już zapisane — pokazujemy aktualne pytanie.", "info")
            return redirect(url_for("test"))

        if not odpowiedz or odpowiedz not in {"A", "B", "C", "D"}:
            # Licznik (F1) wysyła formularz automatycznie po upływie czasu, nawet
            # bez zaznaczonej odpowiedzi — bez tego uczestnik dostawałby "Zaznacz
            # odpowiedź" i wracał na stronę pytania, gdzie licznik od razu znowu
            # wysyłałby pusty formularz w kółko, aż do końca 5-sekundowej tolerancji.
            limit_minal = (
                test_dict["limit_czasu_min"] is not None
                and datetime.now() >= oblicz_termin(podejscie["data_rozpoczecia"], test_dict["limit_czasu_min"])
            )
            if limit_minal:
                with baza() as conn:
                    _zamknij_podejscie_z_powodu_czasu(conn, token)
                return redirect(url_for("wynik"))
            flash("Zaznacz odpowiedź, aby przejść dalej.", "blad")
            return redirect(url_for("test"))

        teraz = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with baza() as conn:
            # Zapis odpowiedzi od razu (L1) — przetrwa utratę ciasteczka/sesji.
            # UNIQUE(token, pytanie_id) + OR IGNORE chroni przed duplikatem (B8).
            conn.execute(
                "INSERT OR IGNORE INTO odpowiedzi_uzytkownika (token, pytanie_id, odpowiedz, data_wyslania) VALUES (?, ?, ?, ?)",
                (token, int(pytanie_id), odpowiedz, teraz),
            )
            # UPDATE...WHERE indeks_pytania=? to atomowe zabezpieczenie: jeśli
            # dwa równoczesne żądania (podwójne kliknięcie „Dalej”/„Zakończ
            # test”, albo dwa urządzenia naraz) trafią tu z tym samym stanem,
            # tylko jedno przesunie indeks — drugie po prostu przekierowuje do
            # aktualnego stanu (B8).
            conn.execute(
                "UPDATE podejscia SET indeks_pytania = indeks_pytania + 1 WHERE token = ? AND indeks_pytania = ?",
                (token, indeks),
            )
        return redirect(url_for("test"))

    if indeks >= len(wybrane_pytania_id):
        return redirect(url_for("wynik"))

    biezace_id = wybrane_pytania_id[indeks]
    with baza() as conn:
        wiersz = conn.execute(
            "SELECT id, tresc_pytania, opcja_a, opcja_b, opcja_c, opcja_d FROM pytania WHERE id = ?",
            (biezace_id,),
        ).fetchone()
    pytanie = dict(wiersz)

    pozostalo_s = None
    if test_dict["limit_czasu_min"] is not None:
        termin = oblicz_termin(podejscie["data_rozpoczecia"], test_dict["limit_czasu_min"])
        pozostalo_s = max(0, int((termin - datetime.now()).total_seconds()))

    return render_template(
        "test.html",
        pytanie=pytanie,
        numer=indeks + 1,
        liczba_pytan=len(wybrane_pytania_id),
        test_nazwa=test_dict["nazwa"],
        pozostalo_s=pozostalo_s,
    )


@app.route("/wynik", methods=["GET"])
def wynik():
    token = session.get("token")
    if not token:
        return redirect(url_for("index"))

    with baza() as conn:
        test_wiersz = conn.execute(
            "SELECT t.* FROM tokeny tk JOIN testy t ON t.id = tk.test_id WHERE tk.token = ?", (token,)
        ).fetchone()
        podejscie = conn.execute("SELECT * FROM podejscia WHERE token = ?", (token,)).fetchone()
        if test_wiersz is None or podejscie is None:
            session.pop("token", None)
            return redirect(url_for("index"))
        test_dict = dict(test_wiersz)

        wybrane_pytania_id = json.loads(podejscie["wybrane_pytania"])
        status = podejscie["status"]

        if status == "w_trakcie":
            if sprawdz_i_domknij_jesli_czas_minal(conn, token, podejscie, test_dict):
                status = "czas_minal"
            elif podejscie["indeks_pytania"] < len(wybrane_pytania_id):
                return redirect(url_for("test"))
            else:
                teraz = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    "UPDATE podejscia SET status = 'zakonczone', data_zakonczenia = ? WHERE token = ? AND status = 'w_trakcie'",
                    (teraz, token),
                )
                status = "zakonczone"

        wiersze = conn.execute(
            """
            SELECT ou.odpowiedz AS dana, p.odpowiedz AS poprawna
            FROM odpowiedzi_uzytkownika ou
            JOIN pytania p ON p.id = ou.pytanie_id
            WHERE ou.token = ?
            """,
            (token,),
        ).fetchall()

    poprawne = sum(1 for w in wiersze if w["dana"] == w["poprawna"])
    # Mianownik to liczba wylosowanych pytań podejścia, nie COUNT() udzielonych
    # odpowiedzi (L3) — dla normalnie ukończonego testu te liczby są równe.
    wszystkie = len(wybrane_pytania_id)
    procent = round(100 * poprawne / wszystkie, 1) if wszystkie else 0

    session.pop("token", None)

    teraz = datetime.now()
    pokaz_wynik, komunikat_wynik = wynik_dostepny(test_dict, teraz)

    return render_template(
        "wynik.html",
        poprawne=poprawne,
        wszystkie=wszystkie,
        procent=procent,
        pokaz_wynik=pokaz_wynik,
        komunikat_wynik=komunikat_wynik,
        czas_minal=(status == "czas_minal"),
    )


@app.route("/sprawdz-wynik", methods=["GET", "POST"])
def sprawdz_wynik():
    if request.method == "POST":
        token = (request.form.get("token") or "").strip().upper()
        if not token:
            flash("Podaj token.", "blad")
            return redirect(url_for("sprawdz_wynik"))

        domknij_przeterminowane_podejscia()

        with baza() as conn:
            test_wiersz = conn.execute(
                "SELECT t.* FROM tokeny tk JOIN testy t ON t.id = tk.test_id WHERE tk.token = ?", (token,)
            ).fetchone()
            wiersze = conn.execute(
                "SELECT * FROM arkusz_wynikow WHERE token = ?",
                (token,),
            ).fetchall()

        if not wiersze or test_wiersz is None:
            flash("Nie znaleziono wyników dla podanego tokenu — test mógł nie zostać jeszcze ukończony.", "info")
            return redirect(url_for("sprawdz_wynik"))

        test_dict = dict(test_wiersz)
        teraz = datetime.now()
        pokaz_wynik, komunikat_wynik = wynik_dostepny(test_dict, teraz)
        pokaz_szczegoly, komunikat_szczegoly = szczegoly_dostepne(test_dict, teraz)

        szczegoly = [dict(w) for w in wiersze]
        poprawne = sum(1 for w in szczegoly if w["odpowiedz_uzytkownika"] == w["poprawna_odpowiedz"])
        wszystkie = len(szczegoly)
        procent = round(100 * poprawne / wszystkie, 1) if wszystkie else 0
        return render_template(
            "sprawdz_wynik.html",
            pokaz_formularz=False,
            szczegoly=szczegoly if pokaz_szczegoly else None,
            poprawne=poprawne,
            wszystkie=wszystkie,
            procent=procent,
            pokaz_wynik=pokaz_wynik,
            komunikat_wynik=komunikat_wynik,
            pokaz_szczegoly=pokaz_szczegoly,
            komunikat_szczegoly=komunikat_szczegoly,
        )
    return render_template("sprawdz_wynik.html", pokaz_formularz=True)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        haslo = request.form.get("haslo") or ""
        if secrets.compare_digest(haslo, ADMIN_HASLO):
            session["admin"] = True
            nastepny = bezpieczna_sciezka_powrotu(request.args.get("nastepny")) or url_for("admin_panel")
            return redirect(nastepny)
        flash("Nieprawidłowe hasło.", "blad")
        return redirect(url_for("admin_login"))
    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["POST"])
@csrf_chroniony
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@wymaga_admina
def admin_panel():
    with baza() as conn:
        testy = conn.execute(
            """
            SELECT
                t.id, t.nazwa, t.data_importu, t.liczba_pytan_do_losowania,
                (SELECT COUNT(*) FROM pytania p WHERE p.test_id = t.id) AS liczba_pytan,
                (SELECT COUNT(*) FROM tokeny tk WHERE tk.test_id = t.id) AS liczba_tokenow,
                (SELECT COUNT(*) FROM tokeny tk WHERE tk.test_id = t.id AND tk.wykorzystany = 1) AS liczba_wykorzystanych
            FROM testy t
            ORDER BY t.data_importu DESC
            """
        ).fetchall()
    return render_template("admin_panel.html", testy=[dict(w) for w in testy])


@app.route("/admin/import", methods=["GET", "POST"])
@wymaga_admina
@csrf_chroniony
def admin_import():
    if request.method == "POST":
        plik = request.files.get("plik")
        nazwa_testu = (request.form.get("nazwa_testu") or "").strip()
        try:
            liczba_pytan = int(request.form.get("liczba_pytan", "20"))
        except ValueError:
            liczba_pytan = 20

        if not plik or plik.filename == "":
            flash("Wybierz plik .xlsx z pytaniami.", "blad")
            return redirect(url_for("admin_import"))
        if not nazwa_testu:
            flash("Podaj nazwę testu.", "blad")
            return redirect(url_for("admin_import"))
        if liczba_pytan < 1:
            flash("Liczba losowanych pytań musi być dodatnia.", "blad")
            return redirect(url_for("admin_import"))

        dane_pliku = plik.read()
        pytania, bledy = wczytaj_i_zwaliduj_plik_pytan(dane_pliku)
        return render_template(
            "admin_import_podglad.html",
            nazwa_testu=nazwa_testu,
            liczba_pytan=liczba_pytan,
            pytania=pytania,
            bledy=bledy,
            plik_base64=base64.b64encode(dane_pliku).decode("ascii"),
        )
    return render_template("admin_import.html")


@app.route("/admin/import/zatwierdz", methods=["POST"])
@wymaga_admina
@csrf_chroniony
def admin_import_zatwierdz():
    """Drugi krok importu (L5) — dane pliku wracają zakodowane w ukrytym polu z
    ekranu podglądu i są walidowane ponownie (odporne na spreparowany
    formularz), dopiero potem trafiają do bazy."""
    nazwa_testu = (request.form.get("nazwa_testu") or "").strip()
    try:
        liczba_pytan = int(request.form.get("liczba_pytan", "20"))
    except ValueError:
        liczba_pytan = 20
    try:
        dane_pliku = base64.b64decode(request.form.get("plik_base64", ""), validate=True)
    except (binascii.Error, ValueError):
        flash("Nie udało się odczytać przesłanego pliku — spróbuj zaimportować ponownie.", "blad")
        return redirect(url_for("admin_import"))

    pytania, bledy = wczytaj_i_zwaliduj_plik_pytan(dane_pliku)
    if bledy:
        flash("Plik zawiera błędy — popraw je i wgraj plik ponownie.", "blad")
        return redirect(url_for("admin_import"))
    if not nazwa_testu:
        flash("Podaj nazwę testu.", "blad")
        return redirect(url_for("admin_import"))

    try:
        test_id, liczba, liczba_pytan_ustawiona = importuj_pytania(nazwa_testu, pytania, liczba_pytan)
    except BladImportu as e:
        flash(str(e), "blad")
        return redirect(url_for("admin_import"))

    if liczba_pytan_ustawiona < liczba_pytan:
        flash(
            f"Uwaga: plik ma tylko {liczba} pytań, więc losowanie ustawiono na "
            f"{liczba_pytan_ustawiona} (zamiast żądanych {liczba_pytan}).",
            "info",
        )
    flash(f"Zaimportowano {liczba} pytań jako test '{nazwa_testu}' (losowanie: {liczba_pytan_ustawiona} na podejście).", "ok")
    return redirect(url_for("admin_test", test_id=test_id))


@app.route("/admin/import/przyklad", methods=["POST"])
@wymaga_admina
@csrf_chroniony
def admin_import_przyklad():
    with baza() as conn:
        nazwa_testu = "Przykładowy test"
        licznik = 1
        while conn.execute("SELECT 1 FROM testy WHERE nazwa = ?", (nazwa_testu,)).fetchone():
            licznik += 1
            nazwa_testu = f"Przykładowy test {licznik}"

    test_id, liczba, liczba_pytan = importuj_pytania(nazwa_testu, PRZYKLADOWE_PYTANIA.copy())
    flash(f"Wgrano przykładowy test '{nazwa_testu}' ({liczba} pytań).", "ok")
    return redirect(url_for("admin_test", test_id=test_id))


@app.route("/admin/szablon-pytan.xlsx")
@wymaga_admina
def admin_szablon():
    skoroszyt = openpyxl.Workbook()
    arkusz = skoroszyt.active
    arkusz.append(["tresc_pytania", "opcja_a", "opcja_b", "opcja_c", "opcja_d", "odpowiedz", "wyjasnienie"])
    arkusz.append([
        "Przykładowe pytanie 1?", "Odpowiedź A", "Odpowiedź B", "Odpowiedź C", "Odpowiedź D", "A",
        "Kolumna wyjasnienie jest opcjonalna — można ją usunąć.",
    ])
    arkusz.append([
        "Przykładowe pytanie 2?", "Odpowiedź A", "Odpowiedź B", "Odpowiedź C", "Odpowiedź D", "C", "",
    ])
    bufor = io.BytesIO()
    skoroszyt.save(bufor)
    bufor.seek(0)
    return send_file(
        bufor,
        as_attachment=True,
        download_name="szablon_pytan.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/admin/testy/<int:test_id>")
@wymaga_admina
def admin_test(test_id):
    domknij_przeterminowane_podejscia(test_id)
    with baza() as conn:
        test = conn.execute("SELECT * FROM testy WHERE id = ?", (test_id,)).fetchone()
        if test is None:
            flash("Nie znaleziono testu.", "blad")
            return redirect(url_for("admin_panel"))
        liczba_pytan = conn.execute(
            "SELECT COUNT(*) AS c FROM pytania WHERE test_id = ?", (test_id,)
        ).fetchone()["c"]
        wyniki = conn.execute(
            "SELECT * FROM zbiorcze_wyniki WHERE test_id = ? ORDER BY data_wyslania DESC", (test_id,)
        ).fetchall()
    return render_template(
        "admin_test.html",
        test=dict(test),
        liczba_pytan=liczba_pytan,
        wyniki=[dict(w) for w in wyniki],
    )


@app.route("/admin/testy/<int:test_id>/tokeny", methods=["GET", "POST"])
@wymaga_admina
@csrf_chroniony
def admin_tokeny(test_id):
    domknij_przeterminowane_podejscia(test_id)
    with baza() as conn:
        test = conn.execute("SELECT * FROM testy WHERE id = ?", (test_id,)).fetchone()
    if test is None:
        flash("Nie znaleziono testu.", "blad")
        return redirect(url_for("admin_panel"))

    if request.method == "POST":
        try:
            dlugosc = int(request.form.get("dlugosc", "8"))
        except ValueError:
            dlugosc = 8
        lista_tekst = (request.form.get("lista_uczestnikow") or "").strip()

        if dlugosc < 4 or dlugosc > 20:
            flash("Długość tokenu powinna być od 4 do 20 znaków.", "blad")
        elif lista_tekst:
            przypisania = [linia.strip() for linia in lista_tekst.splitlines() if linia.strip()]
            if len(przypisania) > 500:
                flash("Lista może zawierać maksymalnie 500 osób naraz.", "blad")
            else:
                try:
                    nowe_tokeny = wygeneruj_tokeny(test_id, len(przypisania), dlugosc, przypisania=przypisania)
                except ValueError as e:
                    flash(str(e), "blad")
                else:
                    # Zapisane w sesji i odczytane raz po przekierowaniu (Post/Redirect/Get,
                    # B10) — bez tego F5 po wygenerowaniu tokenów tworzyłoby je ponownie.
                    session["nowe_tokeny"] = nowe_tokeny
                    flash(f"Wygenerowano {len(nowe_tokeny)} nowych, przypisanych tokenów.", "ok")
        else:
            try:
                liczba = int(request.form.get("liczba", "0"))
            except ValueError:
                liczba = 0
            if liczba < 1 or liczba > 500:
                flash("Podaj liczbę tokenów od 1 do 500 albo wklej listę uczestników.", "blad")
            else:
                try:
                    nowe_tokeny = wygeneruj_tokeny(test_id, liczba, dlugosc)
                except ValueError as e:
                    flash(str(e), "blad")
                else:
                    session["nowe_tokeny"] = nowe_tokeny
                    flash(f"Wygenerowano {len(nowe_tokeny)} nowych tokenów.", "ok")

        return redirect(url_for("admin_tokeny", test_id=test_id))

    nowe_tokeny = session.pop("nowe_tokeny", None)

    with baza() as conn:
        # Status tokenu (UI8): brak podejścia -> "wolny", w_trakcie/zakonczone
        # wprost z podejscia.status.
        tokeny = conn.execute(
            """
            SELECT
                tk.token, tk.wykorzystany, tk.data_utworzenia, tk.data_wykorzystania, tk.przypisany,
                COALESCE(pj.status, 'wolny') AS status
            FROM tokeny tk
            LEFT JOIN podejscia pj ON pj.token = tk.token
            WHERE tk.test_id = ?
            ORDER BY tk.data_utworzenia DESC
            """,
            (test_id,),
        ).fetchall()

    return render_template(
        "admin_tokeny.html",
        test=dict(test),
        tokeny=[dict(t) for t in tokeny],
        nowe_tokeny=nowe_tokeny,
    )


def datetime_local_na_storage(wartosc):
    """Konwersja z formatu pola <input type="datetime-local"> (bez sekund) do
    formatu przechowywanego w bazie. Puste/nieprawidłowe wejście daje None."""
    if not wartosc:
        return None
    try:
        return datetime.strptime(wartosc, "%Y-%m-%dT%H:%M").strftime(FORMAT_DATY)
    except ValueError:
        return None


def storage_na_datetime_local(wartosc):
    """Odwrotność datetime_local_na_storage — do wstępnego wypełnienia formularza."""
    if not wartosc:
        return ""
    try:
        return datetime.strptime(wartosc, FORMAT_DATY).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return ""


@app.route("/admin/testy/<int:test_id>/ustawienia", methods=["GET", "POST"])
@wymaga_admina
@csrf_chroniony
def admin_ustawienia_testu(test_id):
    with baza() as conn:
        test = conn.execute("SELECT * FROM testy WHERE id = ?", (test_id,)).fetchone()
        liczba_pytan_w_banku = conn.execute(
            "SELECT COUNT(*) AS c FROM pytania WHERE test_id = ?", (test_id,)
        ).fetchone()["c"]
    if test is None:
        flash("Nie znaleziono testu.", "blad")
        return redirect(url_for("admin_panel"))

    if request.method == "POST":
        liczba_pytan_tekst = (request.form.get("liczba_pytan_do_losowania") or "").strip()
        if liczba_pytan_tekst:
            try:
                liczba_pytan_do_losowania = int(liczba_pytan_tekst)
                if liczba_pytan_do_losowania < 1:
                    raise ValueError
            except ValueError:
                flash("Liczba losowanych pytań musi być dodatnią liczbą.", "blad")
                return redirect(url_for("admin_ustawienia_testu", test_id=test_id))
            if liczba_pytan_do_losowania > liczba_pytan_w_banku:
                flash(
                    f"Uwaga: w banku jest tylko {liczba_pytan_w_banku} pytań, więc losowanie ustawiono na tyle "
                    f"(zamiast żądanych {liczba_pytan_do_losowania}).",
                    "info",
                )
                liczba_pytan_do_losowania = liczba_pytan_w_banku
        else:
            liczba_pytan_do_losowania = None

        limit_tekst = (request.form.get("limit_czasu_min") or "").strip()
        limit_czasu_min = None
        if limit_tekst:
            try:
                limit_czasu_min = int(limit_tekst)
                if limit_czasu_min < 1:
                    raise ValueError
            except ValueError:
                flash("Limit czasu musi być dodatnią liczbą minut (albo puste pole — brak limitu).", "blad")
                return redirect(url_for("admin_ustawienia_testu", test_id=test_id))

        tryb_szczegolow = request.form.get("tryb_szczegolow", "po_zamknieciu")
        wynik_widoczny = request.form.get("wynik_widoczny", "od_razu")
        if tryb_szczegolow not in TRYBY_SZCZEGOLOW or wynik_widoczny not in TRYBY_WYNIKU:
            flash("Nieprawidłowe ustawienia widoczności.", "blad")
            return redirect(url_for("admin_ustawienia_testu", test_id=test_id))

        szczegoly_od = datetime_local_na_storage(request.form.get("szczegoly_od"))
        dostepny_od = datetime_local_na_storage(request.form.get("dostepny_od"))
        dostepny_do = datetime_local_na_storage(request.form.get("dostepny_do"))
        zamkniety = request.form.get("zamkniety") == "on"

        zapisz_ustawienia_testu(
            test_id, limit_czasu_min, tryb_szczegolow, szczegoly_od, wynik_widoczny, dostepny_od, dostepny_do,
            liczba_pytan_do_losowania,
        )
        ustaw_zamkniecie_testu(test_id, zamkniety)

        flash("Zapisano ustawienia testu.", "ok")
        return redirect(url_for("admin_test", test_id=test_id))

    return render_template(
        "admin_ustawienia_testu.html",
        test=dict(test),
        liczba_pytan_w_banku=liczba_pytan_w_banku,
        szczegoly_od_local=storage_na_datetime_local(test["szczegoly_od"]),
        dostepny_od_local=storage_na_datetime_local(test["dostepny_od"]),
        dostepny_do_local=storage_na_datetime_local(test["dostepny_do"]),
    )


@app.route("/admin/tokeny/<token>/reset", methods=["POST"])
@wymaga_admina
@csrf_chroniony
def admin_reset_token(token):
    """Akcja admina (L2) — reset tokenu: kasuje trwające/zakończone podejście
    i dotychczasowe odpowiedzi, uczestnik zaczyna od nowa tym samym tokenem."""
    test_id = request.form.get("test_id")
    if resetuj_token(token):
        flash(f"Token {token} został zresetowany — można go użyć ponownie od nowa.", "ok")
    else:
        flash("Nie znaleziono tokenu.", "blad")
    if test_id and test_id.isdigit():
        return redirect(url_for("admin_tokeny", test_id=int(test_id)))
    return redirect(url_for("admin_panel"))


@app.route("/admin/tokeny/<token>/przypisz", methods=["POST"])
@wymaga_admina
@csrf_chroniony
def admin_przypisz_token(token):
    przypisany = (request.form.get("przypisany") or "").strip()
    test_id = request.form.get("test_id")
    if przypisz_token(token, przypisany):
        flash(f"Zapisano przypisanie dla tokenu {token}.", "ok")
    else:
        flash("Nie znaleziono tokenu.", "blad")
    # test_id musi być liczbą, inaczej url_for rzuciłby błąd budowania adresu
    # dla nieliczbowego wejścia w polu ukrytym formularza (B15).
    if test_id and test_id.isdigit():
        return redirect(url_for("admin_tokeny", test_id=int(test_id)))
    return redirect(url_for("admin_panel"))


@app.route("/admin/tokeny/<token>")
@wymaga_admina
def admin_token_szczegoly(token):
    with baza() as conn:
        token_wiersz = conn.execute("SELECT przypisany, test_id FROM tokeny WHERE token = ?", (token,)).fetchone()
        wiersze = conn.execute("SELECT * FROM arkusz_wynikow WHERE token = ?", (token,)).fetchall()
    if not wiersze:
        flash("Brak wyników dla tego tokenu — test mógł nie zostać jeszcze ukończony.", "info")
        # Wracamy do listy tokenów właściwego testu zamiast do panelu głównego,
        # bo stąd zwykle wchodzi się z listy tokenów konkretnego testu (B20).
        if token_wiersz:
            return redirect(url_for("admin_tokeny", test_id=token_wiersz["test_id"]))
        return redirect(url_for("admin_panel"))
    szczegoly = [dict(w) for w in wiersze]
    poprawne = sum(1 for w in szczegoly if w["odpowiedz_uzytkownika"] == w["poprawna_odpowiedz"])
    return render_template(
        "admin_token_szczegoly.html",
        token=token,
        przypisany=token_wiersz["przypisany"] if token_wiersz else None,
        szczegoly=szczegoly,
        poprawne=poprawne,
        wszystkie=len(szczegoly),
    )


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    # W trybie debug debugger Werkzeuga pozwala na zdalne wykonanie kodu, więc
    # nasłuchujemy tylko lokalnie — w trybie zwykłym zostaje 0.0.0.0 (B4).
    host = "127.0.0.1" if debug_mode else "0.0.0.0"
    app.run(host=host, port=5555, debug=debug_mode, threaded=True)
