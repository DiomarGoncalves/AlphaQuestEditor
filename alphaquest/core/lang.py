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
