@echo off
rem Starts the web games (apps\web) on a local Vite server and opens the menu page.
rem   start.bat              menu page
rem   start.bat microduck    open one game directly (a109, cars, cessna, f16, microduck)
rem The port is 5180, or the next free one; set WEBAPPS_PORT to choose another.
setlocal
cd /d "%~dp0"

if not defined WEBAPPS_PORT set "WEBAPPS_PORT=5180"

set "PAGE=/"
if not "%~1"=="" set "PAGE=/%~1/"

if not exist node_modules (
    echo Installing dependencies...
    call npm ci || (echo npm ci failed. & pause & exit /b 1)
)

echo Starting the web games  (Ctrl+C to stop)
call npm run dev -- --host 127.0.0.1 --port %WEBAPPS_PORT% --open %PAGE%
if errorlevel 1 pause
