@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   Cloud Save Sync - installation automatique (Windows)
echo ============================================================

:: --- trouve Python (py launcher, install connu, puis PATH) ---
set "PY="
where py >nul 2>nul && set "PY=py" && goto :pyok
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe" && goto :pyok
where python >nul 2>nul && set "PY=python"
:pyok
if "%PY%"=="" (
    echo ERREUR : Python 3.10+ introuvable. Installe-le depuis https://www.python.org/downloads/
    pause
    exit /b 1
)
echo Python : %PY%

:: --- rclone embarque ? sinon on le telecharge ---
if not exist "vendor\windows-amd64\rclone.exe" (
    echo Telechargement de rclone...
    %PY% scripts\fetch_rclone.py || (echo ERREUR fetch_rclone; pause; exit /b 1)
)

:: --- choix du provider ---
echo.
echo Choisis ton cloud :
echo   1) onedrive-local  = dossier OneDrive DEJA synchronise en local (RECOMMANDE,
echo                        aucun OAuth, marche aussi avec un compte pro/ecole)
echo   2) gdrive-local    = dossier Google Drive local (Google Drive for desktop)
echo   3) dropbox-local   = dossier Dropbox local
echo   4) autre remote rclone (onedrive OAuth, gdrive, dropbox...) - necessite rclone config
set /p CHOIX="Ton choix [1]: "
if "%CHOIX%"=="" set CHOIX=1
if "%CHOIX%"=="1" set "REMOTE=onedrive-local"
if "%CHOIX%"=="2" set "REMOTE=gdrive-local"
if "%CHOIX%"=="3" set "REMOTE=dropbox-local"
if "%CHOIX%"=="4" (
    set "REMOTE=onedrive"
    echo.
    echo Connexion du compte cloud a rclone : choisis "n" (new remote),
    echo nomme-le "onedrive" (ou gdrive, dropbox...) puis connecte-toi dans le navigateur.
    echo (erreur AADSTS700016 sur un compte pro/ecole ? -> choisis 1) onedrive-local a la place)
    "vendor\windows-amd64\rclone.exe" config
)

:: --- cree/met a jour la config de l'app ---
%PY% -c "from savesync import core; cfg=core.load_config(); cfg['remote']='%REMOTE%'; core.save_config(cfg); print('remote:', cfg['remote'], '->', core.config_path())"

echo.
echo Scan automatique des dossiers de sauvegardes...
%PY% savesync.py --cli scan --auto

echo.
echo Premier sync vers le cloud...
%PY% savesync.py --cli sync

echo.
echo ============================================================
echo   Termine ! Lancement de l'interface graphique...
echo   (pense a cliquer sur "Auto-sync" dans l'app)
echo ============================================================
start "" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
