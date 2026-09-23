"""Funkcje pomocnicze wspólne dla wielu plików testowych."""

import re


def przejdz_caly_test(klient, token, litera_odpowiedzi="B"):
    """Loguje się tokenem i odpowiada `litera_odpowiedzi` na każde pytanie,
    aż appka przekieruje na stronę wyniku. Zwraca ostatnią odpowiedź (stronę wyniku)."""
    odpowiedz = klient.post("/", data={"token": token}, follow_redirects=True)
    while True:
        dopasowanie = re.search(rb'name="pytanie_id" value="(\d+)"', odpowiedz.data)
        assert dopasowanie, f"Nie znaleziono pytania na stronie: {odpowiedz.data[:300]!r}"
        pytanie_id = dopasowanie.group(1).decode()
        odpowiedz = klient.post(
            "/test",
            data={"pytanie_id": pytanie_id, "odpowiedz": litera_odpowiedzi},
            follow_redirects=True,
        )
        if b"Poprawne odpowiedzi" in odpowiedz.data:
            return odpowiedz
