from flask import Flask, request, render_template, redirect, url_for, session
import pandas as pd
import os
import random

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Załaduj pytania z pliku Excel
pytania_df = pd.read_excel('pytania.xlsx')
#temp1 = pytania_df[:5]
# print(temp1)
# Przygotowanie słownika z poprawnymi odpowiedziami
# Zakładam, że kolumna z ID pytania to pierwsza kolumna (0), a kolumna z poprawnymi odpowiedziami to siódma kolumna (6)
poprawne_odpowiedzi = pd.Series(pytania_df.iloc[:, 6].values, index=pytania_df.iloc[:, 0]).to_dict()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form.get('email')
        #print("test_index1")
        # Sprawdź, czy email już istnieje w bazie danych
        session['email'] = email  # Zapisz email do sesji
        #print(f"email przekazany: {email}")
        #print(f"email w sesji:{session['email']}")

        # Przekieruj do ścieżki '/test', gdzie są losowane pytania
        return redirect(url_for('test'))
    #print("test_index2")
    return render_template('index.html')


@app.route('/test', methods=['GET', 'POST'])
def test():
    #print("test1")
    if 'email' in session:
        print(f"email w sesji: {session['email']}")
    else:
        print("Brak email w sesji.")
        # Tutaj można dodać przekierowanie z powrotem do '/', aby zmusić użytkownika do wprowadzenia emaila
    if 'email' not in session:
        # Jeśli adres email nie jest w sesji, przekieruj do strony głównej.
        return redirect(url_for('index'))
    email = session['email']
    nazwa_pliku = os.path.join("odpowiedzi", f"wyniki_{email.replace('@', '_').replace('.', '_')}.xlsx")

    # Sprawdź, czy istnieje już plik z wynikami dla tego e-maila
    if os.path.exists(nazwa_pliku):
        # Jeśli plik istnieje, wyświetl komunikat zamiast formularza testu
        komunikat = "Już wypełniłeś ten test. Dziękujemy za udział!"
        return render_template('komunikat.html', komunikat=komunikat)

    if request.method == 'POST':
        # Tu powinno być przetwarzanie odpowiedzi, ale to pomijamy,
        # ponieważ odpowiedzi będą przetwarzane w '/wynik'
        #print("test2")
        return redirect(url_for('wynik'))  # Zmienione przekierowanie
    else:
        #print(pytania_df.columns)
        wybrane_pytania = pytania_df.sample(20)
        # Konwersja DataFrame na listę słowników
        #print(wybrane_pytania.columns)
        pytania_do_wyswietlenia = wybrane_pytania.to_dict('records')
        #print(f"test3{pytania_do_wyswietlenia}")
        return render_template('test.html', pytania=pytania_do_wyswietlenia)


@app.route('/wynik', methods=['POST', 'GET'])
def wynik():
    if request.method == 'POST':
        odpowiedzi_uzytkownika = request.form
        email = session.get('email')  # Pobierz email z sesji
        if not email:
            # Przekieruj z powrotem do '/', aby ponownie zebrać email
            return redirect(url_for('index'))

        poprawne = 0
        for pytanie_id, odpowiedz_uzytkownika in odpowiedzi_uzytkownika.items():
            try:
                pytanie_id_int = int(pytanie_id)
                if pytanie_id_int in poprawne_odpowiedzi and poprawne_odpowiedzi[
                    pytanie_id_int] == odpowiedz_uzytkownika:
                    poprawne += 1
            except ValueError:
                # Pomija nieprawidłowe ID pytania lub dodatkowe dane formularza
                continue

        wszystkie = len(odpowiedzi_uzytkownika)

        # Przygotuj DataFrame z odpowiedziami
        odpowiedzi_df = pd.DataFrame(list(odpowiedzi_uzytkownika.items()), columns=['ID Pytania', 'Odpowiedź'])
        nazwa_pliku = os.path.join("odpowiedzi", f"wyniki_{email.replace('@', '_').replace('.', '_')}.xlsx")

        # Sprawdź, czy istnieje już plik z wynikami dla tego e-maila
        if os.path.exists(nazwa_pliku):
            # Jeśli tak, wczytaj istniejący plik i dołącz nowe odpowiedzi
            istniejace_odpowiedzi_df = pd.read_excel(nazwa_pliku)
            odpowiedzi_df = pd.concat([istniejace_odpowiedzi_df, odpowiedzi_df], ignore_index=True)

        # Zapisz/aktualizuj plik z odpowiedziami
        odpowiedzi_df.to_excel(nazwa_pliku, index=False)

        # Możesz tutaj dodać logikę do obliczenia wyniku, jeśli jest to potrzebne
        return render_template('wynik.html', poprawne=poprawne, wszystkie=wszystkie)
    else:
        return redirect(url_for('test'))




if __name__ == '__main__':
    app.run(debug=True)
