#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

VERSION="$(tr -d '\r\n' < VERSION)"
VENV=".build-venv-linux"
RELEASE_DIR="release"

echo "==========================================="
echo " Alpha Quest Editor - Linux ONEFILE Builder"
echo " Version: $VERSION"
echo "==========================================="

command -v python3 >/dev/null 2>&1 || { echo "Python 3 nao encontrado."; exit 1; }

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r requirements.txt -r requirements-build.txt
PYTHONPATH="$PWD" "$VENV/bin/python" tests/test_core.py

rm -rf build dist
mkdir -p "$RELEASE_DIR"
"$VENV/bin/python" -m PyInstaller --noconfirm --clean AlphaQuestEditor.spec

if [ ! -f dist/AlphaQuestEditor ]; then
  echo "ERRO: dist/AlphaQuestEditor nao foi gerado."
  exit 1
fi

OUT="$RELEASE_DIR/AlphaQuestEditor-v${VERSION}-Linux-x64"
cp dist/AlphaQuestEditor "$OUT"
chmod +x "$OUT"
sha256sum "$OUT" > "$OUT.sha256"

echo "Build Linux onefile pronta: $OUT"
