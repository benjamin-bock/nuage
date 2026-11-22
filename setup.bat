@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   Cloud Save Sync - automatic setup (Windows)
echo ============================================================

:: --- find Python (py launcher, known install, then PATH) ---
set "PY="
where py >nul 2>nul && set "PY=py" && goto :pyok
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe" && goto :pyok
where python >nul 2>nul && set "PY=python"
:pyok
if "%PY%"=="" (
    echo ERROR: Python 3.10+ not found. Install it from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo Python: %PY%

:: --- bundled rclone? otherwise download it ---
if not exist "vendor\windows-amd64\rclone.exe" (
    echo Downloading rclone...
    %PY% scripts\fetch_rclone.py || (echo ERROR fetch_rclone; pause; exit /b 1)
)

:: --- choose the provider ---
echo.
echo Choose your cloud:
echo   1) onedrive-local  = OneDrive folder ALREADY synced locally (RECOMMENDED,
echo                        no OAuth, also works with work/school accounts)
echo   2) gdrive-local    = local Google Drive folder (Google Drive for desktop)
echo   3) dropbox-local   = local Dropbox folder
echo   4) other rclone remote (onedrive OAuth, gdrive, dropbox...) - needs rclone config
set /p CHOIX="Your choice [1]: "
if "%CHOIX%"=="" set CHOIX=1
if "%CHOIX%"=="1" set "REMOTE=onedrive-local"
if "%CHOIX%"=="2" set "REMOTE=gdrive-local"
if "%CHOIX%"=="3" set "REMOTE=dropbox-local"
if "%CHOIX%"=="4" (
    set "REMOTE=onedrive"
    echo.
    echo Connect your cloud account to rclone: choose "n" (new remote),
    echo name it "onedrive" (or gdrive, dropbox...) then sign in in the browser.
    echo (AADSTS700016 error on a work/school account? -> pick 1) onedrive-local instead)
    "vendor\windows-amd64\rclone.exe" config
)

:: --- create/update the app config ---
%PY% -c "from savesync import core; cfg=core.load_config(); cfg['remote']='%REMOTE%'; core.save_config(cfg); print('remote:', cfg['remote'], '->', core.config_path())"

echo.
echo Scanning save folders automatically...
%PY% savesync.py --cli scan --auto

echo.
echo First sync to the cloud...
%PY% savesync.py --cli sync

echo.
set /p STARTUP="Launch Cloud Save Sync automatically at Windows startup? [Y/n]: "
if /i not "%STARTUP%"=="n" %PY% -c "from savesync import core; core.set_autostart(True)"

echo.
echo ============================================================
echo   Done! Launching the GUI (no console window)...
echo   (the app syncs once on startup; click "Auto-sync" to keep syncing)
echo ============================================================
:: windowless interpreter (pythonw) so the GUI opens without a terminal window
set "PYW="
if exist "%PY:python.exe=pythonw.exe%" set "PYW=%PY:python.exe=pythonw.exe%"
if "%PYW%"=="" where pythonw >nul 2>nul && set "PYW=pythonw"
if "%PYW%"=="" where pyw >nul 2>nul && set "PYW=pyw"
if "%PYW%"=="" set "PYW=%PY%"
start "" "%PYW%" "%~dp0savesync.py"
