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

:: --- connexion du compte cloud a rclone (une seule fois, navigateur) ---
echo.
echo Connexion du compte cloud a rclone : choisis "n" (new remote),
echo nomme-le "onedrive" (ou gdrive, dropbox...) puis connecte-toi dans le navigateur.
echo (Si c'est deja fait, ferme simplement cette fenetre : Ctrl+C puis "n"... ou reponds et reconfigure.)
"vendor\windows-amd64\rclone.exe" config

:: --- cree la config de l'app si absente (remote par defaut : onedrive) ---
%PY% -c "from savesync import core, os; p=core.config_path(); os.path.exists(str(p)) or core.save_config(core.load_config()); print('config:', p)"

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
