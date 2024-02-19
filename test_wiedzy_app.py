from flask import Flask, request, render_template, redirect, url_for, session
import pandas as pd
import os
import random

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Ustawienie liczby pytań do losowania
LICZBA_PYTAN = 5  # Możesz zmienić tę wartość przed uruchomieniem aplikacji

# Wczytanie pytań z pliku Excel i przygotowanie słownika z poprawnymi odpowiedziami
pytania_df = pd.read_excel('pytania.xlsx')
poprawne_odpowiedzi = pd.Series(pytania_df.iloc[:, 6].values, index=pytania_df.iloc[:, 0]).to_dict()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form.get('email')
        session['email'] = email
        return redirect(url_for('test'))
    return render_template('index.html')

@app.route('/test', methods=['GET', 'POST'])
def test():
    if 'email' not in session:
        return redirect(url_for('index'))

    email = session['email']
    print(email)
    nazwa_pliku = os.path.join("odpowiedzi", f"wyniki_{email.replace('@', '_').replace('.', '_')}.xlsx")

    if os.path.exists(nazwa_pliku):
        komunikat = "Już wypełniłeś ten test. Dziękujemy za udział!"
        return render_template('komunikat.html', komunikat=komunikat)

    wybrane_pytania = pytania_df.sample(LICZBA_PYTAN)
    pytania_do_wyswietlenia = wybrane_pytania.to_dict('records')
    return render_template('test.html', pytania=pytania_do_wyswietlenia)

@app.route('/wynik', methods=['POST', 'GET'])
def wynik():
    if request.method == 'POST':
        email = session.get('email')
        if not email:
            return redirect(url_for('index'))

        dane_do_df = [{"ID Pytania": int(pytanie_id), "Odpowiedź Użytkownika": odp, "Prawidłowa Odpowiedź": poprawne_odpowiedzi.get(int(pytanie_id), "Brak danych")} for pytanie_id, odp in request.form.items() if pytanie_id.isdigit()]

        odpowiedzi_df = pd.DataFrame(dane_do_df)
        nazwa_pliku = os.path.join("odpowiedzi", f"wyniki_{email.replace('@', '_').replace('.', '_')}.xlsx")

        if os.path.exists(nazwa_pliku):
            istniejace_odpowiedzi_df = pd.read_excel(nazwa_pliku)
            odpowiedzi_df = pd.concat([istniejace_odpowiedzi_df, odpowiedzi_df], ignore_index=True)

        odpowiedzi_df.to_excel(nazwa_pliku, index=False)

        poprawne = sum(odpowiedzi_df["Odpowiedź Użytkownika"] == odpowiedzi_df["Prawidłowa Odpowiedź"])
        wszystkie = len(request.form)

        return render_template('wynik.html', poprawne=poprawne, wszystkie=wszystkie)
    else:
        return redirect(url_for('test'))

if __name__ == '__main__':
    app.run(debug=True)
