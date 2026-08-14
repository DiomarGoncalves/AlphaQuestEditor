#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

VERSION="$(tr -d '\r\n' < VERSION)"
VENV=".build-venv-linux"
RELEASE_DIR="release"

echo "==========================================="
echo " Alpha Quest Editor - Linux Builder"
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

cp README.md CHANGELOG.md LICENSE THIRD_PARTY_NOTICES.md dist/AlphaQuestEditor/
tar -C dist -czf "$RELEASE_DIR/AlphaQuestEditor-v${VERSION}-Linux-x64.tar.gz" AlphaQuestEditor
sha256sum "$RELEASE_DIR/AlphaQuestEditor-v${VERSION}-Linux-x64.tar.gz" > "$RELEASE_DIR/AlphaQuestEditor-v${VERSION}-Linux-x64.sha256"

echo "Build Linux pronta em $RELEASE_DIR/"
