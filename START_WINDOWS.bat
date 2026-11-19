@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 ( echo Blad instalacji; pause & exit /b 1 )
py scripts\blix_import.py
if errorlevel 1 ( echo Brak dostepu do Blix lub niepoprawny feed. Sprawdz komunikaty powyzej. )
cd site
start "" "http://localhost:8000"
py -m http.server 8000
pause
