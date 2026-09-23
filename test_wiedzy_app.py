import io
import json
import os
import secrets
from datetime import datetime
from functools import wraps

import pandas as pd
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for

from db import (
    BladImportu,
    baza,
    importuj_test_z_dataframe,
    inicjalizuj,
    losowy_kod,
    przypisz_token,
    wygeneruj_tokeny,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(BASE_DIR, "flask_session")
SECRET_KEY_FILE = os.path.join(BASE_DIR, ".flask_secret_key")
ADMIN_HASLO_FILE = os.path.join(BASE_DIR, ".admin_haslo")

os.makedirs(SESSION_DIR, exist_ok=True)

# Przykładowy zestaw pytań do jednoklikowego wgrania w panelu (/admin/import/przyklad)
PRZYKLADOWE_PYTANIA = pd.DataFrame(
    [
        {"tresc_pytania": "Jaka jest stolica Polski?", "opcja_a": "Kraków", "opcja_b": "Warszawa",
         "opcja_c": "Wrocław", "opcja_d": "Poznań", "odpowiedz": "B"},
        {"tresc_pytania": "Ile kontynentów liczy Ziemia?", "opcja_a": "5", "opcja_b": "6",
         "opcja_c": "7", "opcja_d": "8", "odpowiedz": "C"},
        {"tresc_pytania": "Ile wynosi liczba Pi w przybliżeniu do dwóch miejsc po przecinku?",
         "opcja_a": "3,12", "opcja_b": "3,14", "opcja_c": "3,16", "opcja_d": "3,18", "odpowiedz": "B"},
        {"tresc_pytania": "W którym roku zakończyła się II wojna światowa?", "opcja_a": "1943",
         "opcja_b": "1944", "opcja_c": "1945", "opcja_d": "1946", "odpowiedz": "C"},
        {"tresc_pytania": "Jaki gaz jest najbardziej rozpowszechniony w atmosferze Ziemi?",
         "opcja_a": "Tlen", "opcja_b": "Azot", "opcja_c": "Dwutlenek węgla", "opcja_d": "Wodór", "odpowiedz": "B"},
    ]
)


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


def get_server_session():
    """Zwraca (sid, dane) danych sesji trzymanych po stronie serwera. Ciasteczko
    przeglądarki przechowuje wyłącznie losowy identyfikator, nigdy treść pytań
    ani poprawnych odpowiedzi."""
    sid = session.get("sid")
    if sid:
        try:
            with open(_plik_sesji(sid), "r", encoding="utf-8") as f:
                return sid, json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    sid = secrets.token_urlsafe(32)
    session["sid"] = sid
    return sid, {}


def save_server_session(sid, dane):
    with open(_plik_sesji(sid), "w", encoding="utf-8") as f:
        json.dump(dane, f)


def clear_server_session(sid):
    session.pop("sid", None)
    try:
        os.remove(_plik_sesji(sid))
    except FileNotFoundError:
        pass


def _plik_sesji(sid):
    return os.path.join(SESSION_DIR, f"{sid}.json")


def waliduj_i_zuzyj_token(token):
    """Atomowo sprawdza jednorazowy token i oznacza go jako wykorzystany —
    pojedyncze zapytanie UPDATE...WHERE wykorzystany=0 gwarantuje w SQLite, że
    dwie osoby nie zużyją tego samego tokenu równocześnie. Zwraca id testu,
    do którego token daje dostęp, albo None, jeśli token jest nieprawidłowy
    lub już wykorzystany."""
    teraz = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with baza() as conn:
        cur = conn.execute(
            "UPDATE tokeny SET wykorzystany = 1, data_wykorzystania = ? WHERE token = ? AND wykorzystany = 0",
            (teraz, token),
        )
        if cur.rowcount != 1:
            return None
        wiersz = conn.execute("SELECT test_id FROM tokeny WHERE token = ?", (token,)).fetchone()
    return wiersz["test_id"]


app.jinja_env.globals["csrf_token"] = generuj_csrf_token


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        token = (request.form.get("token") or "").strip().upper()
        if not token:
            flash("Podaj token dostępu.", "blad")
            return redirect(url_for("index"))

        test_id = waliduj_i_zuzyj_token(token)
        if test_id is None:
            flash("Nieprawidłowy lub już wykorzystany token dostępu.", "blad")
            return redirect(url_for("index"))

        sid, dane = get_server_session()
        dane["token"] = token
        dane["test_id"] = test_id
        dane.pop("wybrane_pytania_id", None)
        dane.pop("udzielone_odpowiedzi", None)
        dane.pop("indeks_pytania", None)
        save_server_session(sid, dane)
        return redirect(url_for("test"))
    return render_template("index.html")


@app.route("/test", methods=["GET", "POST"])
def test():
    sid, dane = get_server_session()
    token = dane.get("token")
    test_id = dane.get("test_id")
    if not token or not test_id:
        return redirect(url_for("index"))

    wybrane_pytania_id = dane.get("wybrane_pytania_id")
    if not wybrane_pytania_id:
        with baza() as conn:
            test_wiersz = conn.execute(
                "SELECT liczba_pytan_do_losowania FROM testy WHERE id = ?", (test_id,)
            ).fetchone()
            liczba_pytan = test_wiersz["liczba_pytan_do_losowania"] if test_wiersz else 20
            wiersze = conn.execute(
                "SELECT id FROM pytania WHERE test_id = ? ORDER BY RANDOM() LIMIT ?",
                (test_id, liczba_pytan),
            ).fetchall()
        wybrane_pytania_id = [w["id"] for w in wiersze]
        dane["wybrane_pytania_id"] = wybrane_pytania_id
        dane["udzielone_odpowiedzi"] = {}
        dane["indeks_pytania"] = 0
        save_server_session(sid, dane)

    if not wybrane_pytania_id:
        # Test bez pytań (B12) — bez tego GET /test i GET /wynik przekierowują
        # do siebie nawzajem w nieskończoność.
        clear_server_session(sid)
        flash("Ten test nie ma jeszcze żadnych pytań. Skontaktuj się z organizatorem.", "blad")
        return redirect(url_for("index"))

    udzielone_odpowiedzi = dane.get("udzielone_odpowiedzi", {})
    indeks = dane.get("indeks_pytania", 0)

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
            flash("Zaznacz odpowiedź, aby przejść dalej.", "blad")
            return redirect(url_for("test"))

        udzielone_odpowiedzi[pytanie_id] = odpowiedz
        indeks += 1
        dane["udzielone_odpowiedzi"] = udzielone_odpowiedzi
        dane["indeks_pytania"] = indeks
        save_server_session(sid, dane)

        if indeks >= len(wybrane_pytania_id):
            return redirect(url_for("wynik"))
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

    return render_template(
        "test.html",
        pytanie=pytanie,
        numer=indeks + 1,
        liczba_pytan=len(wybrane_pytania_id),
    )


@app.route("/wynik", methods=["GET"])
def wynik():
    sid, dane = get_server_session()
    token = dane.get("token")
    if not token:
        return redirect(url_for("index"))

    wybrane_pytania_id = dane.get("wybrane_pytania_id") or []
    udzielone_odpowiedzi = dane.get("udzielone_odpowiedzi") or {}
    if not wybrane_pytania_id or len(udzielone_odpowiedzi) < len(wybrane_pytania_id):
        return redirect(url_for("test"))

    teraz = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with baza() as conn:
        juz_zapisane = conn.execute(
            "SELECT 1 FROM odpowiedzi_uzytkownika WHERE token = ? LIMIT 1", (token,)
        ).fetchone()
        if not juz_zapisane:
            conn.executemany(
                """
                INSERT INTO odpowiedzi_uzytkownika (token, pytanie_id, odpowiedz, data_wyslania)
                VALUES (?, ?, ?, ?)
                """,
                [(token, int(pid), odp, teraz) for pid, odp in udzielone_odpowiedzi.items()],
            )
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
    wszystkie = len(wiersze)

    clear_server_session(sid)

    return render_template("wynik.html", poprawne=poprawne, wszystkie=wszystkie)


@app.route("/sprawdz-wynik", methods=["GET", "POST"])
def sprawdz_wynik():
    if request.method == "POST":
        token = (request.form.get("token") or "").strip().upper()
        if not token:
            flash("Podaj token.", "blad")
            return redirect(url_for("sprawdz_wynik"))

        with baza() as conn:
            wiersze = conn.execute(
                "SELECT * FROM arkusz_wynikow WHERE token = ?",
                (token,),
            ).fetchall()

        if not wiersze:
            flash("Nie znaleziono wyników dla podanego tokenu — test mógł nie zostać jeszcze ukończony.", "info")
            return redirect(url_for("sprawdz_wynik"))

        szczegoly = [dict(w) for w in wiersze]
        poprawne = sum(1 for w in szczegoly if w["odpowiedz_uzytkownika"] == w["poprawna_odpowiedz"])
        return render_template(
            "sprawdz_wynik.html",
            pokaz_formularz=False,
            szczegoly=szczegoly,
            poprawne=poprawne,
            wszystkie=len(szczegoly),
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

        try:
            df = pd.read_excel(plik)
        except Exception:
            flash("Nie udało się odczytać pliku — sprawdź, czy to poprawny plik .xlsx.", "blad")
            return redirect(url_for("admin_import"))

        try:
            test_id, liczba, liczba_pytan_ustawiona = importuj_test_z_dataframe(nazwa_testu, df, liczba_pytan)
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
    return render_template("admin_import.html")


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

    test_id, liczba, liczba_pytan = importuj_test_z_dataframe(nazwa_testu, PRZYKLADOWE_PYTANIA.copy())
    flash(f"Wgrano przykładowy test '{nazwa_testu}' ({liczba} pytań).", "ok")
    return redirect(url_for("admin_test", test_id=test_id))


@app.route("/admin/szablon-pytan.xlsx")
@wymaga_admina
def admin_szablon():
    df = pd.DataFrame(
        [
            {"tresc_pytania": "Przykładowe pytanie 1?", "opcja_a": "Odpowiedź A", "opcja_b": "Odpowiedź B",
             "opcja_c": "Odpowiedź C", "opcja_d": "Odpowiedź D", "odpowiedz": "A"},
            {"tresc_pytania": "Przykładowe pytanie 2?", "opcja_a": "Odpowiedź A", "opcja_b": "Odpowiedź B",
             "opcja_c": "Odpowiedź C", "opcja_d": "Odpowiedź D", "odpowiedz": "C"},
        ]
    )
    bufor = io.BytesIO()
    df.to_excel(bufor, index=False)
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
        tokeny = conn.execute(
            """
            SELECT token, wykorzystany, data_utworzenia, data_wykorzystania, przypisany
            FROM tokeny WHERE test_id = ? ORDER BY data_utworzenia DESC
            """,
            (test_id,),
        ).fetchall()

    return render_template(
        "admin_tokeny.html",
        test=dict(test),
        tokeny=[dict(t) for t in tokeny],
        nowe_tokeny=nowe_tokeny,
    )


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
