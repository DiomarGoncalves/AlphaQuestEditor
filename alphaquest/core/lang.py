from __future__ import annotations

import re
from pathlib import Path

from .snbt_scan import _scan_string, _skip_ws_comments, find_matching, find_key_value_start


def _unescape(value: str) -> str:
    return value.replace(r"\n", "\n").replace(r'\"', '"').replace(r"\\", "\\")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', r'\"')


def _parse_string_list(text: str, i: int) -> tuple[str, int]:
    end = find_matching(text, i, "[", "]")
    if end < 0:
        return "", len(text)
    vals: list[str] = []
    p = i + 1
    while p < end:
        p = _skip_ws_comments(text, p)
        while p < end and text[p] in ",;":
            p = _skip_ws_comments(text, p + 1)
        if p >= end:
            break
        if text[p] in ('"', "'"):
            j = _scan_string(text, p)
            vals.append(_unescape(text[p + 1:j - 1]))
            p = j
        else:
            j = p
            while j < end and text[j] not in "\r\n,;]":
                j += 1
            raw = text[p:j].strip()
            if raw:
                vals.append(raw)
            p = j + 1
    return "\n".join(vals), end + 1


def parse_lang_snbt(path: Path) -> dict[str, str]:
    """Read FTB language SNBT.

    FTB quest descriptions/subtitles are commonly arrays of strings rather than a
    single scalar. Alpha Quest Editor exposes them as newline-separated text while
    preserving list format when they are saved again.
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {}
    i = 0
    n = len(text)
    key_re = re.compile(r"[A-Za-z0-9_./+-]+")
    while i < n:
        i = _skip_ws_comments(text, i)
        if i >= n:
            break
        if text[i] in "{},[]":
            i += 1
            continue
        if text[i] in ('"', "'"):
            j = _scan_string(text, i)
            key = text[i + 1:j - 1]
            i = j
        else:
            m = key_re.match(text, i)
            if not m:
                i += 1
                continue
            key = m.group(0)
            i = m.end()
        i = _skip_ws_comments(text, i)
        if i >= n or text[i] != ":":
            continue
        i = _skip_ws_comments(text, i + 1)
        if i >= n:
            break
        if text[i] in ('"', "'"):
            j = _scan_string(text, i)
            out[key] = _unescape(text[i + 1:j - 1])
            i = j
        elif text[i] == "[":
            value, i = _parse_string_list(text, i)
            out[key] = value
        else:
            j = i
            while j < n and text[j] not in "\r\n,}":
                j += 1
            out[key] = text[i:j].strip()
            i = j
    return out


def _format_value(value: str, as_list: bool) -> str:
    if as_list:
        lines = value.split("\n")
        body = "\n".join(f'\t\t"{_escape(line)}"' for line in lines)
        return "[\n" + body + "\n\t]"
    return f'"{_escape(value).replace(chr(10), r"\n")}"'


def write_lang_value(path: Path, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        as_list = "\n" in value or key.endswith((".quest_desc", ".chapter_subtitle"))
        rendered = _format_value(value, as_list)
        path.write_text("{\n" + f"\t{key}:{rendered}\n" + "}\n", encoding="utf-8")
        return

    text = path.read_text(encoding="utf-8", errors="replace")
    start = find_key_value_start(text, key)
    if start >= 0:
        if text[start] == "[":
            end = find_matching(text, start, "[", "]")
            as_list = True
        elif text[start] in ('"', "'"):
            end = _scan_string(text, start) - 1
            as_list = False
        else:
            end = start
            while end < len(text) and text[end] not in "\r\n,}":
                end += 1
            end -= 1
            as_list = "\n" in value or key.endswith((".quest_desc", ".chapter_subtitle"))
        if end >= start:
            rendered = _format_value(value, as_list)
            text = text[:start] + rendered + text[end + 1:]
    else:
        as_list = "\n" in value or key.endswith((".quest_desc", ".chapter_subtitle"))
        rendered = _format_value(value, as_list)
        pos = text.rfind("}")
        line = f"\t{key}:{rendered}\n"
        if pos < 0:
            text = "{\n" + line + "}\n"
        else:
            text = text[:pos].rstrip() + "\n" + line + text[pos:]
    path.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Multi-format language support (SNBT flat/split + JSON5 native split)
# ---------------------------------------------------------------------------

def _flatten_lang_value(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def _structured_lang_value(key: str, value: str, existing=None):
    as_list = isinstance(existing, list) or "\n" in value or key.endswith((".quest_desc", ".chapter_subtitle", ".quest_subtitle"))
    return value.split("\n") if as_list else value


def discover_locales(quest_root: Path, storage_format: str = "snbt") -> list[str]:
    lang_root = Path(quest_root) / "lang"
    if not lang_root.exists():
        return []
    found = {p.stem for p in lang_root.glob("*.snbt")}
    found.update(p.name for p in lang_root.iterdir() if p.is_dir() and p.name not in ("recovery",))
    if storage_format == "json5":
        found.update(p.name for p in lang_root.iterdir() if p.is_dir())
    return sorted(found)


def load_locale_tree(quest_root: Path, locale: str, storage_format: str = "snbt") -> dict[str, str]:
    """Load a locale independent of whether it is flat or split."""
    quest_root = Path(quest_root)
    lang_root = quest_root / "lang"
    out: dict[str, str] = {}
    if storage_format == "json5":
        from .json5_codec import load as load_json5
        loc = lang_root / locale
        if loc.exists():
            for p in sorted(loc.rglob("*.json5")):
                try:
                    data = load_json5(p)
                except Exception:
                    continue
                if isinstance(data, dict):
                    out.update({str(k): _flatten_lang_value(v) for k, v in data.items()})
        return out

    # Legacy flat file remains authoritative when present, then split files may
    # overlay it. This mirrors the addon workflow where split files are edits.
    flat = lang_root / f"{locale}.snbt"
    if flat.exists():
        out.update(parse_lang_snbt(flat))
    loc = lang_root / locale
    if loc.exists():
        for p in sorted(loc.rglob("*.snbt")):
            if p.name.endswith(".snbt_merged"):
                continue
            out.update(parse_lang_snbt(p))
    return out


def _translation_relative_file(key: str, owner_lookup: dict[str, str] | None = None) -> str:
    owner_lookup = owner_lookup or {}
    parts = key.split(".")
    if len(parts) < 3:
        return "misc"
    kind, oid = parts[0], parts[1]
    if kind in ("file", "chapter", "chapter_group", "reward_table"):
        return {"file":"file", "chapter":"chapter", "chapter_group":"chapter_group", "reward_table":"reward_table"}[kind]
    if kind in ("quest", "task", "reward", "quest_link", "image"):
        return "chapters/" + owner_lookup.get(oid, "_orphaned")
    return "misc"


def _find_existing_split_file(lang_root: Path, locale: str, key: str, suffix: str):
    loc = lang_root / locale
    if not loc.exists():
        return None
    for p in sorted(loc.rglob(f"*{suffix}")):
        try:
            if suffix == ".json5":
                from .json5_codec import load as loader
                data = loader(p)
                if isinstance(data, dict) and key in data:
                    return p
            elif key in parse_lang_snbt(p):
                return p
        except Exception:
            continue
    return None


def write_translation_value(quest_root: Path, locale: str, key: str, value: str, storage_format: str = "snbt", owner_lookup: dict[str, str] | None = None) -> Path:
    """Write one translation to the correct flat/split file and return it."""
    quest_root = Path(quest_root)
    lang_root = quest_root / "lang"
    lang_root.mkdir(parents=True, exist_ok=True)
    if storage_format == "json5":
        from .json5_codec import load as load_json5, save as save_json5
        target = _find_existing_split_file(lang_root, locale, key, ".json5")
        if target is None:
            target = lang_root / locale / (_translation_relative_file(key, owner_lookup) + ".json5")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if target.exists():
            try: data = load_json5(target)
            except Exception: data = {}
        if not isinstance(data, dict): data = {}
        data[key] = _structured_lang_value(key, value, data.get(key))
        save_json5(target, data)
        return target

    split_dir = lang_root / locale
    existing = _find_existing_split_file(lang_root, locale, key, ".snbt") if split_dir.exists() else None
    if existing is not None or split_dir.exists():
        target = existing or split_dir / (_translation_relative_file(key, owner_lookup) + ".snbt")
        write_lang_value(target, key, value)
        return target
    target = lang_root / f"{locale}.snbt"
    write_lang_value(target, key, value)
    return target
