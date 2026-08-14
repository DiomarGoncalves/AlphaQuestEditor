# Publicando uma versão no GitHub

## Opção A — build local no Windows

1. Atualize o arquivo `VERSION`.
2. Atualize `CHANGELOG.md` e `RELEASE_NOTES.md`.
3. Dê dois cliques em `BUILD_RELEASE.bat`.
4. Confirme que `release/` contém o ZIP Windows e o ZIP de código-fonte.
5. No GitHub, crie uma tag no formato `v0.8.0-alpha`.
6. Crie uma Release usando a mesma tag.
7. Anexe os arquivos de `release/`.

## Opção B — build automático no GitHub

O repositório inclui `.github/workflows/release.yml`.

Ao enviar uma tag `v*`, o GitHub Actions:

1. roda os testes;
2. compila Windows x64;
3. compila Linux x64;
4. empacota os binários;
5. cria a GitHub Release e anexa os pacotes.

Exemplo:

```bash
git tag v0.8.0-alpha
git push origin v0.8.0-alpha
```

Acompanhe a aba **Actions** do repositório antes de divulgar a Release.


## Single-file builds (FIX3)
Windows releases are built with PyInstaller ONEFILE. The distributable artifact is `release/AlphaQuestEditor-v0.8.0-alpha-Windows-x64.exe`; do not distribute the temporary `build/` directory. A one-file build may start slightly slower because bundled libraries are unpacked to a temporary runtime directory.
