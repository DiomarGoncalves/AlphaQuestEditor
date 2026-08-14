@echo off
setlocal
cd /d "%~dp0"
title Alpha Quest Editor - Gerar Release
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_tools\build_release.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
  echo [ERRO] A compilacao falhou. Veja as mensagens acima.
) else (
  echo [OK] Release gerada. Abra a pasta release.
)
echo.
pause
exit /b %EXITCODE%
