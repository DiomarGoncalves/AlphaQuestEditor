# Compilando o Alpha Quest Editor

## Windows — jeito fácil

1. Instale Python 3.11 ou 3.12.
2. Extraia/clone o projeto.
3. Dê dois cliques em **`BUILD_RELEASE.bat`**.
4. Espere os testes e a compilação.
5. Abra a pasta **`release/`**.

O script gera:

- `AlphaQuestEditor-v<VERSAO>-Windows-x64.exe` — executável ONEFILE pronto para distribuir;
- `AlphaQuestEditor-v<VERSAO>-Source.zip` — snapshot do código-fonte;
- `SHA256SUMS.txt`;
- `RELEASE_NOTES.md`.

`BUILD_WINDOWS_ONLY.bat` gera somente o executável Windows e checksum.

Não distribua `build/`. A pasta `dist/` contém a saída bruta do PyInstaller; prefira o arquivo renomeado em `release/`.

## Linux

```bash
chmod +x build_linux.sh
./build_linux.sh
```

O resultado fica em:

```text
release/AlphaQuestEditor-v<VERSAO>-Linux-x64
release/AlphaQuestEditor-v<VERSAO>-Linux-x64.sha256
```

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

## ONEFILE

O projeto usa PyInstaller **ONEFILE** para as releases. O executável/binário pode iniciar um pouco mais devagar porque Qt/Python e demais dependências são desempacotadas em uma pasta temporária durante a inicialização.

## Testes antes da release

O builder cancela automaticamente se `tests/test_core.py` falhar. A suíte cobre o núcleo SNBT, JSON5, conversão de formatos, idiomas e operações principais do Quest Book.
