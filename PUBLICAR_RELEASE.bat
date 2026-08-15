@echo off
setlocal
cd /d "%~dp0"

echo.
echo Iniciando publicacao automatica do Alpha Quest Editor...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0publicar_release.ps1"

if errorlevel 1 (
    echo.
    echo A publicacao encontrou um erro.
    pause
    exit /b 1
)

echo.
echo Publicacao enviada ao GitHub Actions.
pause
