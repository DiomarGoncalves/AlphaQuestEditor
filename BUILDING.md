# Compilando o Alpha Quest Editor

## Windows — jeito fácil

1. Instale Python 3.11 ou 3.12.
2. Extraia/clone o projeto.
3. Dê dois cliques em **`BUILD_RELEASE.bat`**.
4. Espere os testes e a compilação.
5. Abra a pasta **`release/`**.

O script gera:

- `AlphaQuestEditor-v<VERSAO>-Windows-x64.zip`
- `AlphaQuestEditor-v<VERSAO>-Source.zip`
- `SHA256SUMS.txt`
- `RELEASE_NOTES.md`

`BUILD_WINDOWS_ONLY.bat` gera apenas o pacote Windows.

## Linux

```bash
chmod +x build_linux.sh
./build_linux.sh
```

O resultado fica em `release/AlphaQuestEditor-v<VERSAO>-Linux-x64.tar.gz`.

## Executar sem compilar

Windows:

```text
run.bat
```

Linux:

```bash
chmod +x run_linux.sh
./run_linux.sh
```

## Build manual

```bash
python -m venv .venv
# ative a venv
python -m pip install -r requirements.txt -r requirements-build.txt
python tests/test_core.py
python -m PyInstaller --noconfirm --clean AlphaQuestEditor.spec
```

O projeto usa build **onedir** por padrão, deixando o executável e suas dependências em uma pasta. Isso facilita diagnóstico durante a fase alpha.


## Single-file builds (FIX3)
Windows releases are built with PyInstaller ONEFILE. The distributable artifact is `release/AlphaQuestEditor-v0.8.0-alpha-Windows-x64.exe`; do not distribute the temporary `build/` directory. A one-file build may start slightly slower because bundled libraries are unpacked to a temporary runtime directory.
