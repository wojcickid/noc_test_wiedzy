@echo off
echo Sprawdzanie i instalowanie brakujacych pakietow...
pip install pandas
pip install flask
pip install openpyxl

echo Uruchamianie aplikacji Flask...
cd C:\Users\wojci\PycharmProjects\test_wiedzy
set FLASK_APP=test_wiedzy_app.py
set FLASK_ENV=development
flask run


pause