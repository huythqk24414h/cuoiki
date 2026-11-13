@echo off
setlocal
cd /d "%~dp0"
title Liquidity Lab
set "LAB_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%LAB_PYTHON%" goto bundled
set "LAB_PYTHON=C:\Users\DELL\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%LAB_PYTHON%" goto bundled
where py >nul 2>nul
if not errorlevel 1 goto pylauncher
python --version >nul 2>nul
if not errorlevel 1 goto systempython
echo Python 3.11 or newer is required. Please install Python and open this file again.
pause
exit /b 1
:bundled
"%LAB_PYTHON%" "%~dp0launch.py"
goto finished
:pylauncher
py -3 "%~dp0launch.py"
goto finished
:systempython
python "%~dp0launch.py"
:finished
if errorlevel 1 (
  echo Liquidity Lab could not start. See the error above.
  pause
)
endlocal
