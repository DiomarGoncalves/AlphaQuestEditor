from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def backup_questbook(quest_root: Path) -> Path | None:
    if not quest_root.exists():
        return None
    root = quest_root.parent / ".alphaquest" / "backups"
    root.mkdir(parents=True, exist_ok=True)
    target = root / datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    shutil.copytree(quest_root, target)
    return target
