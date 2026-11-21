@echo off
REM Lance Cloud Save Sync (GUI par defaut). Usage : run.bat --cli sync
where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0savesync.py" %*
) else (
    python "%~dp0savesync.py" %*
)
