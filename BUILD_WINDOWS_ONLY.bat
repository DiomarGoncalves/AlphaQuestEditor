@echo off
setlocal
cd /d "%~dp0"
title Alpha Quest Editor - Build Windows
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_tools\build_release.ps1" -WindowsOnly
set EXITCODE=%ERRORLEVEL%
echo.
if "%EXITCODE%"=="0" (
  echo [OK] Build Windows gerada em release.
) else (
  echo [ERRO] Build Windows falhou.
)
pause
exit /b %EXITCODE%
