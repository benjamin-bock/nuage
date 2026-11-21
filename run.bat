@echo off
REM Launches Cloud Save Sync (GUI by default). Usage: run.bat --cli sync
where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0savesync.py" %*
) else (
    python "%~dp0savesync.py" %*
)
