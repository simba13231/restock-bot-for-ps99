@echo off
title PS99 Restock Bot

echo ==================================================
echo   PS99 Restock Bot - Starting
echo ==================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on this computer.
    echo.
    echo Go to https://www.python.org/downloads/ and install
    echo Python. IMPORTANT: on the first install screen, check
    echo the box that says "Add python.exe to PATH" before
    echo clicking Install.
    echo.
    echo After installing Python, double-click this file again.
    echo.
    pause
    exit /b 1
)

echo Checking dependencies (this may take a minute the first time)...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo Something went wrong installing dependencies.
    echo Scroll up to see the error message above.
    echo.
    pause
    exit /b 1
)

echo.
echo Starting the bot...
echo.

python ps99_restock_bot.py

echo.
echo The bot has stopped.
pause
