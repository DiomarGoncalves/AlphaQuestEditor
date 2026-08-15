$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host " Alpha Quest Editor - Publicador de Release" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path ".git")) {
    throw "Execute este arquivo na raiz do repositorio AlphaQuestEditor."
}

if (-not (Test-Path "VERSION")) {
    throw "Arquivo VERSION nao encontrado."
}

$version = (Get-Content "VERSION" -Raw).Trim()

if ([string]::IsNullOrWhiteSpace($version)) {
    throw "O arquivo VERSION esta vazio."
}

$tag = "v$version"
$branch = (git branch --show-current).Trim()

if ([string]::IsNullOrWhiteSpace($branch)) {
    throw "Nao foi possivel identificar a branch atual."
}

Write-Host "Branch : $branch" -ForegroundColor Yellow
Write-Host "Versao : $version" -ForegroundColor Yellow
Write-Host "Tag    : $tag" -ForegroundColor Yellow
Write-Host ""

Write-Host "Sincronizando versao do aplicativo..." -ForegroundColor Cyan
python scripts/sync_version.py
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao sincronizar VERSION com alphaquest/version.py."
}

# Garante que estamos atualizados antes de publicar.
git fetch origin --tags

# Nao sobrescreve uma release/tag antiga por engano.
$localTag = git tag --list $tag
$remoteTag = git ls-remote --tags origin "refs/tags/$tag"

if ($localTag -or $remoteTag) {
    Write-Host ""
    Write-Host "ERRO: A tag $tag ja existe." -ForegroundColor Red
    Write-Host "Altere o arquivo VERSION para uma nova versao e execute novamente." -ForegroundColor Yellow
    exit 1
}

Write-Host "Adicionando alteracoes..." -ForegroundColor Cyan
git add -A

$staged = git diff --cached --name-only

if ($staged) {
    Write-Host "Criando commit da release..." -ForegroundColor Cyan
    git commit -m "release: $tag"
} else {
    Write-Host "Nenhuma alteracao pendente para commit." -ForegroundColor DarkGray
}

Write-Host "Enviando branch $branch..." -ForegroundColor Cyan
git push origin $branch

Write-Host "Criando tag $tag..." -ForegroundColor Cyan
git tag -a $tag -m "Alpha Quest Editor $tag"

Write-Host "Enviando tag..." -ForegroundColor Cyan
git push origin $tag

Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host " RELEASE DISPARADA COM SUCESSO" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "O GitHub Actions agora vai:" -ForegroundColor White
Write-Host "  1. testar o projeto" -ForegroundColor White
Write-Host "  2. compilar Windows x64" -ForegroundColor White
Write-Host "  3. compilar Linux x64" -ForegroundColor White
Write-Host "  4. criar a GitHub Release" -ForegroundColor White
Write-Host "  5. anexar os binarios automaticamente" -ForegroundColor White
Write-Host ""
Write-Host "Tag enviada: $tag" -ForegroundColor Yellow
Write-Host ""
