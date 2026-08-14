#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
VENV=".venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip
  "$VENV/bin/python" -m pip install -r requirements.txt
fi
exec "$VENV/bin/python" -m alphaquest.app
