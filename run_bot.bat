@echo off
:menu
cls
echo ==============================
echo Discord Booking Bot
echo ==============================
echo 1. Start Bot
echo 2. Stop Bot
echo 3. Exit
echo ==============================
set /p choice=Choose an option (1-3): 

if "%choice%"=="1" goto startbot
if "%choice%"=="2" goto stopbot
if "%choice%"=="3" exit
goto menu

:startbot
echo Starting Discord Booking Bot...
python slot_booking_bot.py
echo Bot stopped. Returning to menu...
pause
goto menu

:stopbot
echo Stopping Discord Booking Bot...
taskkill /F /IM python.exe
echo Bot stopped.
pause
goto menu