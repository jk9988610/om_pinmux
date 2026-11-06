@echo off
REM OM6239 PinMux - double-click launcher (no PowerShell needed)
setlocal EnableExtensions
cd /d "%~dp0"

set "PYEXE="
set "PYWEXE="

where pythonw >nul 2>&1 && for /f "delims=" %%I in ('where pythonw') do (
  if not defined PYWEXE set "PYWEXE=%%I"
)
where python >nul 2>&1 && for /f "delims=" %%I in ('where python') do (
  if not defined PYEXE set "PYEXE=%%I"
)
if not defined PYEXE (
  where py >nul 2>&1 && set "PYEXE=py"
)

if not defined PYEXE if not defined PYWEXE (
  echo [om_pinmux] Python not found. Install Python 3 and add it to PATH.
  echo.
  pause
  exit /b 1
)

REM Prefer pythonw so double-click does not leave a console window
if defined PYWEXE (
  start "OM6239 PinMux" /D "%~dp0" "%PYWEXE%" "%~dp0app.py" %*
  exit /b 0
)

if /I "%PYEXE%"=="py" (
  start "OM6239 PinMux" /D "%~dp0" py -3 "%~dp0app.py" %*
  exit /b 0
)

start "OM6239 PinMux" /D "%~dp0" "%PYEXE%" "%~dp0app.py" %*
exit /b 0
