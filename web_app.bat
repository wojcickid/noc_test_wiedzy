@echo off
setlocal

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "WYMAGANIA=%~dp0requirements.txt"
set "ZNACZNIK=%VENV_DIR%\.requirements_synced"

if not exist "%VENV_PY%" (
    echo Brak srodowiska .venv - tworzenie nowego...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Nie udalo sie utworzyc srodowiska wirtualnego. Sprawdz, czy Python jest zainstalowany.
        pause
        exit /b 1
    )
)

rem Instalacja pakietow tylko przy pierwszym starcie (nowe .venv) albo po zmianie
rem requirements.txt - nie przy kazdym uruchomieniu appki (S5, wymaga internetu).
for %%F in ("%WYMAGANIA%") do set "AKTUALNY_ZNACZNIK=%%~tF"
set "POPRZEDNI_ZNACZNIK="
if exist "%ZNACZNIK%" set /p POPRZEDNI_ZNACZNIK=<"%ZNACZNIK%"

if not "%AKTUALNY_ZNACZNIK%"=="%POPRZEDNI_ZNACZNIK%" (
    echo Instalowanie/aktualizowanie pakietow z requirements.txt...
    "%VENV_PY%" -m pip install -r "%WYMAGANIA%"
    if errorlevel 1 (
        echo Instalacja pakietow nie powiodla sie.
        pause
        exit /b 1
    )
    >"%ZNACZNIK%" echo %AKTUALNY_ZNACZNIK%
) else (
    echo Pakiety juz zainstalowane i zgodne z requirements.txt - pomijam instalacje.
)

echo Uruchamianie aplikacji Flask...
"%VENV_PY%" "%~dp0test_wiedzy_app.py"

pause
