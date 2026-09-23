"""Wysyłka maili z tokenami (Etap 6, F3/E6) przez zwykły serwer SMTP — Gmail
i Google Workspace (smtp.gmail.com + hasło do aplikacji), Microsoft 365 albo
dowolny inny. Dane logowania są wyłącznie w pliku config.json (w .gitignore) —
nie trafiają do bazy, do przeglądarki ani do komunikatów o błędach.

Aplikacja widzi tylko błędy zgłoszone od razu przez serwer nadawcy (złe
hasło, brak połączenia, adres odrzucony przy wysyłce). Nieistniejąca skrzynka
po stronie odbiorcy zwykle wychodzi dopiero później, jako zwrotka („Mail
Delivery Subsystem”) na skrzynkę nadawcy — tego aplikacja nie odczytuje.
"""

import json
import os
import re
import smtplib
import ssl
import threading
import time
import uuid
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PLIK = os.path.join(BASE_DIR, "config.json")

# Gmail pozwala wysłać ok. 500 maili dziennie z konta prywatnego (ok. 2000
# z Google Workspace) i źle znosi serie bez przerw — 1 mail na sekundę to
# bezpieczne tempo, a 500 zaproszeń i tak idzie w niecałe 10 minut.
ODSTEP_SEKUNDY = 1
TIMEOUT_SEKUNDY = 20
SZYFROWANIA = {"starttls", "ssl", "brak"}

ZNACZNIKI = {
    "imie": "imię i nazwisko uczestnika (puste, jeśli nie podano)",
    "token": "token uczestnika",
    "link": "link do testu z wpisanym tokenem",
    "nazwa_testu": "nazwa testu",
    "dostepny_do": "do kiedy można rozpocząć test (albo „bez terminu”)",
    "limit_czasu": "limit czasu na test (albo „bez limitu czasu”)",
    "nazwa_nadawcy": "nazwa nadawcy z ustawień poczty",
}

DOMYSLNE_SZABLONY = {
    "zaproszenie": {
        "temat": "Zaproszenie do testu: {nazwa_testu}",
        "tresc": (
            "Dzień dobry,\n"
            "\n"
            "zapraszamy do rozwiązania testu wiedzy „{nazwa_testu}”.\n"
            "\n"
            "Link do testu: {link}\n"
            "Twój token: {token}\n"
            "\n"
            "Limit czasu: {limit_czasu}\n"
            "Test można rozpocząć do: {dostepny_do}\n"
            "\n"
            "Token jest osobisty i jednorazowy — nie przekazuj go innym osobom. Test można "
            "przerwać i wznowić tym samym tokenem, także na innym urządzeniu.\n"
            "\n"
            "Powodzenia!\n"
            "\n"
            "-- \n"
            "{nazwa_nadawcy}\n"
            "W razie pytań skontaktuj się z prowadzącym szkolenie.\n"
        ),
    },
    "przypomnienie": {
        "temat": "Przypomnienie: test {nazwa_testu}",
        "tresc": (
            "Dzień dobry,\n"
            "\n"
            "przypominamy o teście wiedzy „{nazwa_testu}” — nie został jeszcze ukończony.\n"
            "\n"
            "Link do testu: {link}\n"
            "Twój token: {token}\n"
            "\n"
            "Limit czasu: {limit_czasu}\n"
            "Test można rozpocząć do: {dostepny_do}\n"
            "\n"
            "Jeśli test został już rozpoczęty, można go dokończyć tym samym tokenem.\n"
            "\n"
            "Powodzenia!\n"
            "\n"
            "-- \n"
            "{nazwa_nadawcy}\n"
            "W razie pytań skontaktuj się z prowadzącym szkolenie.\n"
        ),
    },
}


class BladPoczty(Exception):
    """Błąd z komunikatem gotowym do pokazania adminowi (nigdy z hasłem)."""


def wczytaj_konfiguracje():
    """Ustawienia serwera z sekcji "smtp" pliku config.json (wzór:
    config.przyklad.json). Rzuca BladPoczty, jeśli pliku nie ma albo jest
    niekompletny."""
    if not os.path.exists(CONFIG_PLIK):
        raise BladPoczty(
            "Brak pliku config.json z ustawieniami serwera poczty — skopiuj config.przyklad.json "
            "jako config.json i uzupełnij (patrz README, sekcja „Wysyłka maili”)."
        )
    try:
        with open(CONFIG_PLIK, "r", encoding="utf-8-sig") as f:
            dane = json.load(f)
    except ValueError as e:
        raise BladPoczty(f"Plik config.json nie jest poprawnym JSON-em ({e}).")
    except OSError:
        raise BladPoczty("Nie udało się odczytać pliku config.json.")

    smtp = dane.get("smtp") if isinstance(dane, dict) else None
    if not isinstance(smtp, dict) or not smtp.get("host"):
        raise BladPoczty("W config.json brakuje sekcji \"smtp\" z polem \"host\".")

    szyfrowanie = str(smtp.get("szyfrowanie") or "starttls").lower()
    if szyfrowanie not in SZYFROWANIA:
        raise BladPoczty("Pole \"szyfrowanie\" w config.json musi mieć wartość starttls, ssl albo brak.")
    try:
        port = int(smtp.get("port") or (465 if szyfrowanie == "ssl" else 587))
    except (TypeError, ValueError):
        raise BladPoczty("Pole \"port\" w config.json musi być liczbą.")

    login = str(smtp.get("login") or "").strip()
    nadawca_email = str(smtp.get("nadawca_email") or login).strip()
    if "@" not in nadawca_email:
        raise BladPoczty("W config.json brakuje adresu nadawcy (\"nadawca_email\" albo login w postaci adresu e-mail).")
    return {
        "host": str(smtp["host"]).strip(),
        "port": port,
        "szyfrowanie": szyfrowanie,
        "login": login,
        "haslo": str(smtp.get("haslo") or ""),
        "nadawca_email": nadawca_email,
    }


def podglad_konfiguracji():
    """(konfiguracja bez hasła, None) albo (None, komunikat błędu) — do panelu."""
    try:
        konfig = wczytaj_konfiguracje()
    except BladPoczty as e:
        return None, str(e)
    podglad = {k: v for k, v in konfig.items() if k != "haslo"}
    podglad["haslo_ustawione"] = bool(konfig["haslo"])
    return podglad, None


def wypelnij_szablon(tekst, dane):
    """Podmienia {znaczniki} na wartości; nieznane zostawia bez zmian."""
    return re.sub(r"\{(\w+)\}", lambda m: str(dane[m[1]]) if m[1] in dane else m[0], tekst)


def nieznane_znaczniki(tekst):
    return sorted(set(re.findall(r"\{(\w+)\}", tekst)) - ZNACZNIKI.keys())


def zbuduj_wiadomosc(konfig, nazwa_nadawcy, adres, temat, tresc):
    wiadomosc = EmailMessage()
    wiadomosc["From"] = formataddr((nazwa_nadawcy, konfig["nadawca_email"]))
    wiadomosc["To"] = adres
    # Temat w jednej linii — znak nowej linii w nagłówku to błąd (i furtka
    # do wstrzyknięcia dodatkowych nagłówków).
    wiadomosc["Subject"] = " ".join(temat.split())
    wiadomosc["Date"] = formatdate(localtime=True)
    wiadomosc["Message-ID"] = make_msgid(domain=konfig["nadawca_email"].rsplit("@", 1)[-1])
    wiadomosc.set_content(tresc)
    return wiadomosc


def _opis_bledu(e):
    if isinstance(e, smtplib.SMTPResponseException):
        tekst = e.smtp_error.decode("utf-8", errors="replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        return f"{e.smtp_code} {' '.join(tekst.split())}"
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


def _polacz(konfig):
    serwer = None
    kontekst = ssl.create_default_context()
    try:
        if konfig["szyfrowanie"] == "ssl":
            serwer = smtplib.SMTP_SSL(konfig["host"], konfig["port"], timeout=TIMEOUT_SEKUNDY, context=kontekst)
        else:
            serwer = smtplib.SMTP(konfig["host"], konfig["port"], timeout=TIMEOUT_SEKUNDY)
            if konfig["szyfrowanie"] == "starttls":
                serwer.starttls(context=kontekst)
        if konfig["login"]:
            serwer.login(konfig["login"], konfig["haslo"])
        return serwer
    except smtplib.SMTPAuthenticationError:
        _zamknij(serwer)
        raise BladPoczty(
            "Serwer poczty odrzucił login lub hasło. Gmail i Google Workspace wymagają hasła do aplikacji "
            "(nie zwykłego hasła do konta) — patrz README."
        )
    except (OSError, smtplib.SMTPException) as e:
        _zamknij(serwer)
        raise BladPoczty(f"Nie udało się połączyć z serwerem poczty {konfig['host']}:{konfig['port']} ({_opis_bledu(e)}).")


def _zamknij(serwer):
    if serwer is None:
        return
    try:
        serwer.quit()
    except Exception:
        pass


def wyslij_mail_testowy(konfig, nazwa_nadawcy, adres):
    """Jeden mail kontrolny z panelu — BladPoczty z opisem, jeśli się nie uda."""
    wiadomosc = zbuduj_wiadomosc(
        konfig, nazwa_nadawcy, adres, "Test wiedzy — mail testowy",
        "To jest mail testowy z aplikacji Test wiedzy.\n\n"
        "Jeśli go widzisz, ustawienia serwera poczty są poprawne.\n",
    )
    serwer = _polacz(konfig)
    try:
        serwer.send_message(wiadomosc)
    except (OSError, smtplib.SMTPException) as e:
        raise BladPoczty(f"Serwer nie przyjął maila ({_opis_bledu(e)}).")
    finally:
        _zamknij(serwer)


def wyslij_serie(konfig, wiadomosci, po_wiadomosci):
    """Wysyła listę (klucz, EmailMessage) jednym połączeniem, z odstępem
    ODSTEP_SEKUNDY. Po każdej wiadomości woła po_wiadomosci(klucz, blad),
    gdzie blad=None oznacza sukces. Odrzucenie jednego adresu nie przerywa
    serii; zerwane połączenie — tak (pozostałe dostają błąd)."""
    serwer = _polacz(konfig)
    try:
        for i, (klucz, wiadomosc) in enumerate(wiadomosci):
            if i and ODSTEP_SEKUNDY:
                time.sleep(ODSTEP_SEKUNDY)
            try:
                serwer.send_message(wiadomosc)
            except smtplib.SMTPRecipientsRefused as e:
                powody = "; ".join(
                    f"{kod} {(opis.decode('utf-8', errors='replace') if isinstance(opis, bytes) else opis)}"
                    for kod, opis in e.recipients.values()
                )
                po_wiadomosci(klucz, f"Serwer odrzucił adres odbiorcy ({' '.join(powody.split())}).")
            except (smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as e:
                po_wiadomosci(klucz, f"Serwer odrzucił wiadomość ({_opis_bledu(e)}).")
            except (OSError, smtplib.SMTPException) as e:
                po_wiadomosci(klucz, f"Przerwane połączenie z serwerem poczty ({_opis_bledu(e)}).")
                for klucz_reszty, _ in wiadomosci[i + 1:]:
                    po_wiadomosci(klucz_reszty, "Nie wysłano — wcześniej przerwane połączenie z serwerem poczty.")
                return
            else:
                po_wiadomosci(klucz, None)
    finally:
        _zamknij(serwer)


# Stan wysyłek w pamięci procesu — wystarcza do strony postępu; trwały wynik
# (wysłany/błąd) każdego maila i tak trafia do bazy przez zapisz_wynik.
_wysylki = {}
_blokada = threading.Lock()


def rozpocznij_wysylke(konfig, opis, zadania, zapisz_wynik, w_tle=True):
    """Uruchamia serię maili (domyślnie w wątku w tle) i zwraca jej id do
    strony postępu. `zadania` to lista {"token", "adres", "wiadomosc"},
    `zapisz_wynik(token, blad)` zapisuje wynik każdego maila w bazie.
    Naraz może trwać tylko jedna wysyłka — dwie równoległe serie z jednego
    konta to prosta droga do blokady przez Gmaila."""
    with _blokada:
        if any(not w["zakonczona"] for w in _wysylki.values()):
            raise BladPoczty("Trwa już inna wysyłka — poczekaj na jej zakończenie.")
        id_wysylki = uuid.uuid4().hex[:12]
        stan = {
            "id": id_wysylki,
            "opis": opis,
            "rozpoczeta": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "zakonczona": False,
            "blad_ogolny": None,
            "pozycje": [{"token": z["token"], "adres": z["adres"], "status": "czeka", "blad": None} for z in zadania],
        }
        _wysylki[id_wysylki] = stan
    pozycje = {p["token"]: p for p in stan["pozycje"]}

    def po_wiadomosci(token, blad):
        zapisz_wynik(token, blad)
        with _blokada:
            pozycje[token]["status"] = "blad" if blad else "wyslany"
            pozycje[token]["blad"] = blad

    def praca():
        try:
            wyslij_serie(konfig, [(z["token"], z["wiadomosc"]) for z in zadania], po_wiadomosci)
        except Exception as e:
            komunikat = str(e) if isinstance(e, BladPoczty) else f"Nieoczekiwany błąd wysyłki ({type(e).__name__})."
            stan["blad_ogolny"] = komunikat
            for pozycja in stan["pozycje"]:
                if pozycja["status"] == "czeka":
                    po_wiadomosci(pozycja["token"], komunikat)
        finally:
            with _blokada:
                stan["zakonczona"] = True

    if w_tle:
        threading.Thread(target=praca, name=f"wysylka-{id_wysylki}", daemon=True).start()
    else:
        praca()
    return id_wysylki


def stan_wysylki(id_wysylki):
    """Kopia stanu wysyłki z licznikami albo None, jeśli nie ma takiej."""
    with _blokada:
        stan = _wysylki.get(id_wysylki)
        if stan is None:
            return None
        kopia = dict(stan, pozycje=[dict(p) for p in stan["pozycje"]])
    kopia["wszystkie"] = len(kopia["pozycje"])
    kopia["wyslane"] = sum(1 for p in kopia["pozycje"] if p["status"] == "wyslany")
    kopia["bledy"] = sum(1 for p in kopia["pozycje"] if p["status"] == "blad")
    return kopia
