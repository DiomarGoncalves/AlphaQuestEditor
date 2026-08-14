from __future__ import annotations

import json
import logging
import os
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..version import APP_NAME, APP_VERSION


def app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "AlphaQuestEditor"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AlphaQuestEditor"
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "alphaquesteditor"


def logs_dir() -> Path:
    p = app_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def configure_logging() -> Path:
    log_path = logs_dir() / "alphaquest.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Avoid duplicate handlers when tests or embedded launches call main twice.
    marker = str(log_path.resolve())
    if not any(getattr(h, "_alphaquest_path", None) == marker for h in root.handlers):
        handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        handler._alphaquest_path = marker  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        root.addHandler(handler)
    logging.getLogger(__name__).info("%s %s starting on %s", APP_NAME, APP_VERSION, platform.platform())
    return log_path


def diagnostic_payload(book=None, mods=None) -> dict:
    payload = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "executable": sys.executable,
        "frozen": bool(getattr(sys, "frozen", False)),
        "logs": str(logs_dir()),
    }
    if book is not None:
        try:
            payload["project"] = {
                "root": str(book.root),
                "quest_root": str(book.quest_root),
                "storage_format": str(book.storage_format),
                "chapters": len(book.chapters),
                "quests": sum(len(c.quests) for c in book.chapters),
                "locales": sorted(set(getattr(book, "available_locales", []) or [])),
            }
        except Exception as exc:
            payload["project_error"] = repr(exc)
    if mods is not None:
        try:
            payload["assets"] = {
                "minecraft_version": str(getattr(mods, "minecraft_version", "auto")),
                "items": len(getattr(mods, "items", {})),
                "images": len(getattr(mods, "images", {})),
                "shapes": len(getattr(mods, "quest_shapes", {})),
                "cache": bool(getattr(mods, "loaded_from_cache", False)),
                "warnings": list(getattr(mods, "errors", []))[:30],
            }
        except Exception as exc:
            payload["assets_error"] = repr(exc)
    return payload


def diagnostic_text(book=None, mods=None) -> str:
    return json.dumps(diagnostic_payload(book, mods), ensure_ascii=False, indent=2)
