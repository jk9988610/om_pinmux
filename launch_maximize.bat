@echo off
REM OM6239 PinMux - start maximized (double-click)
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0launch.bat" --maximize %*
