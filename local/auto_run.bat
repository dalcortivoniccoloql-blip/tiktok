@echo off
cd /d "C:\Users\nicco\Desktop\tiktok"

:: Log con timestamp
set LOG_DIR=logs
if not exist %LOG_DIR% mkdir %LOG_DIR%

for /f "tokens=1-6 delims=/:. " %%a in ("%date% %time%") do (
    set DT=%%c-%%b-%%a_%%d-%%e
)
set LOG_FILE=%LOG_DIR%\run_%DT%.txt

echo ============================================ >> %LOG_FILE%
echo  Auto Run - %date% %time% >> %LOG_FILE%
echo ============================================ >> %LOG_FILE%

:: Genera 1 video (auto-rileva il prossimo script) e pubblica subito su YouTube
py pipeline\main.py --count 1 --upload-youtube --publish-now >> %LOG_FILE% 2>&1

if errorlevel 1 (
    echo ERRORE - vedi %LOG_FILE%
) else (
    echo OK - %LOG_FILE%
)
