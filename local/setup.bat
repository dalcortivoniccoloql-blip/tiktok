@echo off
echo ============================================
echo   Setup Pipeline TikTok
echo ============================================
echo.

py --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato. Installalo da https://py.org
    pause
    exit /b 1
)

echo Installazione dipendenze...
pip install -r requirements.txt

echo.
echo ============================================
echo   Setup completato!
echo ============================================
echo.
echo Comandi disponibili:
echo.
echo   py pipeline\main.py --list
echo     ^> Mostra tutti gli script disponibili
echo.
echo   py pipeline\main.py --count 5
echo     ^> Genera i prossimi 5 video automaticamente
echo.
echo   py pipeline\main.py --script 21 --count 3
echo     ^> Genera 3 video a partire dallo script #21
echo.
echo   py pipeline\main.py --video-only --count 5
echo     ^> Crea solo i video (usando audio gia' esistenti)
echo.
echo   py pipeline\main.py --audio-only --count 10
echo     ^> Crea solo gli audio (piu' veloce, senza video)
echo.
pause
