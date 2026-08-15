from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
PY_VERSION_FILE = ROOT / "alphaquest" / "version.py"

version = VERSION_FILE.read_text(encoding="utf-8").strip()
if not version:
    raise SystemExit("VERSION esta vazio.")

text = PY_VERSION_FILE.read_text(encoding="utf-8")

new_text, count = re.subn(
    r'(?m)^APP_VERSION\s*=\s*["\'][^"\']*["\']\s*$',
    f'APP_VERSION = "{version}"',
    text,
    count=1,
)

if count != 1:
    raise SystemExit("Nao foi possivel localizar APP_VERSION em alphaquest/version.py.")

PY_VERSION_FILE.write_text(new_text, encoding="utf-8", newline="\n")
print(f"Versao sincronizada: {version}")
