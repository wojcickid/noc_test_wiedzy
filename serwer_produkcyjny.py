"""Uruchamia appkę przez produkcyjny serwer WSGI (waitress) zamiast wbudowanego
serwera deweloperskiego Flaska — bez auto-reloadera i debuggera, z prawdziwą
obsługą wielu równoczesnych połączeń.

Użycie:
    python serwer_produkcyjny.py
"""

import os

from waitress import serve

from test_wiedzy_app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5555"))
    threads = int(os.environ.get("WAITRESS_THREADS", "8"))
    print(f"Serwer produkcyjny (waitress) nasłuchuje na http://0.0.0.0:{port}")
    serve(app, host="0.0.0.0", port=port, threads=threads)
