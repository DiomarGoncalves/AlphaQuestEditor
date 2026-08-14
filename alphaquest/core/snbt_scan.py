from __future__ import annotations

import re
from dataclasses import dataclass


_KEY_RE = re.compile(r"[A-Za-z0-9_./:+-]+")


def _skip_ws_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        if text.startswith("//", i):
            end = text.find("\n", i + 2)
            return n if end < 0 else _skip_ws_comments(text, end + 1)
        if text[i] == "#":
            end = text.find("\n", i + 1)
            return n if end < 0 else _skip_ws_comments(text, end + 1)
        break
    return i


def _scan_string(text: str, i: int) -> int:
    quote = text[i]
    i += 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return len(text)


def find_matching(text: str, start: int, open_ch: str, close_ch: str) -> int:
    assert text[start] == open_ch
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch in ('"', "'"):
            i = _scan_string(text, i)
            continue
        if text.startswith("//", i):
            end = text.find("\n", i + 2)
            i = len(text) if end < 0 else end + 1
            continue
        if ch == "#":
            end = text.find("\n", i + 1)
            i = len(text) if end < 0 else end + 1
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def find_key_value_start(text: str, key: str, start: int = 0, end: int | None = None) -> int:
    end = len(text) if end is None else end
    # Quoted and unquoted keys are both accepted by FTB SNBT.
    pattern = re.compile(rf'(?<![A-Za-z0-9_])(?:"{re.escape(key)}"|{re.escape(key)})\s*:')
    m = pattern.search(text, start, end)
    if not m:
        return -1
    return _skip_ws_comments(text, m.end())


def extract_scalar(text: str, key: str, default: str = "") -> str:
    i = find_key_value_start(text, key)
    if i < 0 or i >= len(text):
        return default
    if text[i] in ('"', "'"):
        j = _scan_string(text, i)
        raw = text[i:j]
        try:
            # Most FTB strings in quest data are simple JSON-style strings.
            import json
            if raw.startswith('"'):
                return json.loads(raw)
        except Exception:
            pass
        return raw[1:-1]
    j = i
    while j < len(text) and text[j] not in ",}]\r\n\t ":
        j += 1
    return text[i:j].strip()


def extract_float(text: str, key: str, default: float = 0.0) -> float:
    raw = extract_scalar(text, key, "")
    raw = re.sub(r"[dDfFlLsSbB]$", "", raw)
    try:
        return float(raw)
    except ValueError:
        return default


def extract_compound(text: str, key: str) -> str:
    i = find_key_value_start(text, key)
    if i < 0 or i >= len(text) or text[i] != "{":
        return ""
    j = find_matching(text, i, "{", "}")
    return text[i : j + 1] if j >= 0 else ""


def extract_list(text: str, key: str) -> str:
    i = find_key_value_start(text, key)
    if i < 0 or i >= len(text) or text[i] != "[":
        return ""
    j = find_matching(text, i, "[", "]")
    return text[i : j + 1] if j >= 0 else ""


def split_top_level_compounds(list_text: str) -> list[tuple[int, int, str]]:
    """Return spans relative to list_text for top-level compounds in [ ... ]."""
    out: list[tuple[int, int, str]] = []
    if not list_text:
        return out
    i = 1 if list_text.startswith("[") else 0
    limit = len(list_text) - 1 if list_text.endswith("]") else len(list_text)
    while i < limit:
        i = _skip_ws_comments(list_text, i)
        while i < limit and list_text[i] in ",;":
            i = _skip_ws_comments(list_text, i + 1)
        if i >= limit:
            break
        if list_text[i] == "{":
            j = find_matching(list_text, i, "{", "}")
            if j < 0:
                break
            out.append((i, j + 1, list_text[i : j + 1]))
            i = j + 1
        elif list_text[i] in ('"', "'"):
            i = _scan_string(list_text, i)
        else:
            i += 1
    return out


def extract_string_list(text: str, key: str) -> list[str]:
    raw = extract_list(text, key)
    if not raw:
        return []
    result: list[str] = []
    i = 1
    while i < len(raw) - 1:
        i = _skip_ws_comments(raw, i)
        if i >= len(raw) - 1:
            break
        if raw[i] in ('"', "'"):
            j = _scan_string(raw, i)
            result.append(raw[i + 1 : j - 1])
            i = j
            continue
        m = _KEY_RE.match(raw, i)
        if m:
            result.append(m.group(0))
            i = m.end()
        else:
            i += 1
    return result


def find_top_level_key_value_start(text: str, key: str) -> int:
    """Find a key at the root compound/list level, ignoring nested compounds/lists."""
    i = 0
    curly = square = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ('"', "'"):
            i = _scan_string(text, i); continue
        if text.startswith("//", i):
            end = text.find("\n", i + 2); i = n if end < 0 else end + 1; continue
        if ch == "#":
            end = text.find("\n", i + 1); i = n if end < 0 else end + 1; continue
        if ch == "{": curly += 1; i += 1; continue
        if ch == "}": curly -= 1; i += 1; continue
        if ch == "[": square += 1; i += 1; continue
        if ch == "]": square -= 1; i += 1; continue
        # Root of a compound is depth 1. For bare text, accept depth 0.
        target_depth = 1 if text.lstrip().startswith("{") else 0
        if curly == target_depth and square == 0:
            if ch == '"':
                pass
            m = re.match(r"[A-Za-z0-9_./+\-]+", text[i:])
            if m:
                # re.match above is relative to i; normalize span-compatible token below.
                token = m.group(0)
                mend = i + len(token)
                j = _skip_ws_comments(text, mend)
                if token == key and j < n and text[j] == ":":
                    return _skip_ws_comments(text, j + 1)
                i = mend; continue
            m = None
        i += 1
    return -1


def extract_top_level_scalar(text: str, key: str, default: str = "") -> str:
    i = find_top_level_key_value_start(text, key)
    if i < 0 or i >= len(text): return default
    if text[i] in ('"', "'"):
        j = _scan_string(text, i)
        raw = text[i:j]
        try:
            import json
            if raw.startswith('"'): return json.loads(raw)
        except Exception: pass
        return raw[1:-1]
    j = i
    while j < len(text) and text[j] not in ",}]\r\n\t ": j += 1
    return text[i:j].strip()
