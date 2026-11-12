@echo off
rem Starts bg-sim: the backend serves the built web app on http://127.0.0.1:8765.
rem   start.bat           build the web app if web\dist is missing, then start
rem   start.bat build     rebuild the web app first
setlocal
cd /d "%~dp0"

if not defined BGSIM_PORT_HTTP set "BGSIM_PORT_HTTP=8765"

set "BUILD="
if /i "%~1"=="build" set "BUILD=1"
if not exist "web\dist\index.html" set "BUILD=1"

if defined BUILD (
    pushd web
    if not exist node_modules (
        echo Installing web dependencies...
        call npm ci || (popd & echo npm ci failed. & pause & exit /b 1)
    )
    echo Building the web app...
    call npm run build || (popd & echo Web build failed. & pause & exit /b 1)
    popd
)

rem Open the browser once the server has had a moment to come up.
start "" /b cmd /c "ping -n 4 127.0.0.1 >nul & start "" http://127.0.0.1:%BGSIM_PORT_HTTP%/"

echo Starting bg-sim on http://127.0.0.1:%BGSIM_PORT_HTTP%/  (Ctrl+C to stop)
uv run bgsim
if errorlevel 1 pause
