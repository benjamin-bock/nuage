@echo off
REM Launches Cloud Save Sync. No arguments -> GUI without a console window (pyw/pythonw);
REM with arguments (e.g. run.bat --cli sync) -> CLI in this console.
if not "%~1"=="" goto :cli
where pyw >nul 2>nul && (start "" pyw "%~dp0savesync.py" & exit /b 0)
where pythonw >nul 2>nul && (start "" pythonw "%~dp0savesync.py" & exit /b 0)
:cli
where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0savesync.py" %*
) else (
    python "%~dp0savesync.py" %*
)
