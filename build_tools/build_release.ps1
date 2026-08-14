param(
    [switch]$WindowsOnly
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$Version = (Get-Content (Join-Path $Root "VERSION") -Raw).Trim()
if (-not $Version) { throw "Arquivo VERSION vazio." }

$ReleaseDir = Join-Path $Root "release"
$BuildDir = Join-Path $Root "build"
$DistDir = Join-Path $Root "dist"
$VenvDir = Join-Path $Root ".build-venv"
$StageDir = Join-Path $Root ".release-stage"

function Find-Python {
    $candidates = @(
        @{ Cmd = "py"; Prefix = @("-3.12") },
        @{ Cmd = "py"; Prefix = @("-3.11") },
        @{ Cmd = "py"; Prefix = @("-3") },
        @{ Cmd = "python"; Prefix = @() }
    )
    foreach ($c in $candidates) {
        try {
            $probeArgs = @()
            $probeArgs += $c.Prefix
            $probeArgs += @("-c", "import sys; print(sys.executable)")
            & $c.Cmd @probeArgs *> $null
            if ($LASTEXITCODE -eq 0) { return $c }
        } catch {}
    }
    throw "Python 3 nao encontrado. Instale Python 3.11 ou 3.12 e marque a opcao de adicionar ao PATH."
}

function Invoke-Python($py, [string[]]$Arguments) {
    $cmdArgs = @()
    $cmdArgs += $py.Prefix
    $cmdArgs += $Arguments
    & $py.Cmd @cmdArgs
    if ($LASTEXITCODE -ne 0) { throw "Comando Python falhou: $($Arguments -join ' ')" }
}

Write-Host "===========================================" -ForegroundColor Cyan
Write-Host " Alpha Quest Editor - Release Builder" -ForegroundColor Cyan
Write-Host " Versao: $Version" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan

$py = Find-Python
Write-Host "[1/7] Preparando ambiente de build..."
if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
    Invoke-Python $py @("-m", "venv", $VenvDir)
}
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "[2/7] Instalando/atualizando dependencias..."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Falha ao atualizar pip." }
& $VenvPython -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependencias." }

Write-Host "[3/7] Rodando testes do nucleo..."
$env:PYTHONPATH = $Root
& $VenvPython tests\test_core.py
if ($LASTEXITCODE -ne 0) { throw "Os testes falharam. Build cancelada para evitar publicar uma versao quebrada." }
& $VenvPython -m compileall -q alphaquest main.py
if ($LASTEXITCODE -ne 0) { throw "Falha na compilacao sintatica dos fontes." }
& $VenvPython -c "import PySide6, PIL; import alphaquest.app; print('UI import smoke: OK')"
if ($LASTEXITCODE -ne 0) { throw "Falha no smoke test das dependencias/UI." }

Write-Host "[4/7] Limpando builds anteriores..."
@($BuildDir, $DistDir, $ReleaseDir, $StageDir) | ForEach-Object {
    if (Test-Path $_) { Remove-Item $_ -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

Write-Host "[5/7] Compilando Windows x64 (PyInstaller ONEFILE)..."
& $VenvPython -m PyInstaller --noconfirm --clean AlphaQuestEditor.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

$BuiltExe = Join-Path $DistDir "AlphaQuestEditor.exe"
if (-not (Test-Path $BuiltExe)) {
    throw "AlphaQuestEditor.exe nao foi encontrado em dist. O build onefile falhou."
}

# Release principal: UM unico EXE, sem DLLs/pasta _internal ao lado.
$WindowsExe = Join-Path $ReleaseDir "AlphaQuestEditor-v$Version-Windows-x64.exe"
Copy-Item $BuiltExe -Destination $WindowsExe -Force
Write-Host "      -> $WindowsExe (arquivo unico)" -ForegroundColor Green

if (-not $WindowsOnly) {
    Write-Host "[6/7] Gerando pacote de codigo-fonte..."
    New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
    $excluded = @(".git", ".venv", ".build-venv", ".alphaquest", ".release-stage", "build", "dist", "release", "__pycache__")
    Get-ChildItem -Force $Root | Where-Object { $excluded -notcontains $_.Name } | ForEach-Object {
        Copy-Item $_.FullName -Destination $StageDir -Recurse -Force
    }
    Get-ChildItem $StageDir -Recurse -Directory -Force | Where-Object { $_.Name -eq "__pycache__" } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem $StageDir -Recurse -File -Include *.pyc,*.pyo | Remove-Item -Force -ErrorAction SilentlyContinue

    $SourceZip = Join-Path $ReleaseDir "AlphaQuestEditor-v$Version-Source.zip"
    Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $SourceZip -CompressionLevel Optimal
    Remove-Item $StageDir -Recurse -Force
    Write-Host "      -> $SourceZip" -ForegroundColor Green

    Copy-Item RELEASE_NOTES.md -Destination (Join-Path $ReleaseDir "RELEASE_NOTES.md") -Force
}

Write-Host "[7/7] Gerando checksums SHA-256..."
$HashFile = Join-Path $ReleaseDir "SHA256SUMS.txt"
Get-ChildItem $ReleaseDir -File | Where-Object { $_.Extension -in @(".zip", ".gz", ".exe") } | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($_.Name)"
} | Set-Content $HashFile -Encoding ascii

Write-Host ""
Write-Host "RELEASE PRONTA!" -ForegroundColor Green
Write-Host "Pasta: $ReleaseDir" -ForegroundColor Green
Write-Host ""
Write-Host "Para Linux: rode ./build_linux.sh em uma maquina Linux, ou crie uma tag v$Version no GitHub para o workflow gerar Windows + Linux automaticamente." -ForegroundColor Yellow
