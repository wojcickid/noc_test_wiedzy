@echo off
setlocal

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo Brak srodowiska .venv - tworzenie nowego...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Nie udalo sie utworzyc srodowiska wirtualnego. Sprawdz, czy Python jest zainstalowany.
        pause
        exit /b 1
    )
)

echo Sprawdzanie i instalowanie brakujacych pakietow...
"%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Instalacja pakietow nie powiodla sie.
    pause
    exit /b 1
)

echo Uruchamianie aplikacji (serwer produkcyjny waitress)...
"%VENV_PY%" "%~dp0serwer_produkcyjny.py"

pause
