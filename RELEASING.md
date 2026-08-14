# Publicando uma versão no GitHub

## Opção A — build local no Windows

1. Atualize `VERSION`.
2. Atualize `CHANGELOG.md` e `RELEASE_NOTES.md`.
3. Rode `tests/test_core.py` ou simplesmente execute `BUILD_RELEASE.bat`.
4. Confirme que `release/` contém o EXE Windows, ZIP de código-fonte e checksums.
5. No GitHub, crie uma tag igual à versão, por exemplo `v0.9.6.1-alpha`.
6. Crie a Release usando a mesma tag.
7. Anexe os arquivos de `release/`.

## Opção B — build automático no GitHub

O repositório inclui `.github/workflows/release.yml`.

Ao enviar uma tag `v*`, o GitHub Actions:

1. roda os testes;
2. compila Windows x64 ONEFILE;
3. compila Linux x64 ONEFILE;
4. baixa os artefatos no job de publicação;
5. cria ou atualiza a GitHub Release.

Exemplo:

```bash
git add .
git commit -m "release: v0.9.6.1-alpha"
git push

git tag v0.9.6.1-alpha
git push origin v0.9.6.1-alpha
```

Acompanhe a aba **Actions** antes de divulgar a Release.

## Assets esperados

```text
AlphaQuestEditor-v0.9.6.1-alpha-Windows-x64.exe
AlphaQuestEditor-v0.9.6.1-alpha-Linux-x64
Source code (zip)       # gerado automaticamente pelo GitHub para a tag
Source code (tar.gz)    # gerado automaticamente pelo GitHub para a tag
```

O build local também gera `AlphaQuestEditor-v0.9.6.1-alpha-Source.zip` e `SHA256SUMS.txt` para uso manual.
