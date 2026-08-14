from __future__ import annotations

"""Small dependency-free JSON5 reader/writer used by Alpha Quest Editor.

It intentionally supports the JSON5 features FTB Quests uses: comments, trailing
commas, single/double quoted strings, bare identifier keys, hexadecimal numbers,
Infinity/NaN and leading + signs.  The writer emits stable, human-readable JSON5
with two-space indentation and trailing commas.
"""

import math
import re
from pathlib import Path

from .io_utils import atomic_write_text
from typing import Any


class JSON5Error(ValueError):
    pass


_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"[+-]?(?:0[xX][0-9a-fA-F]+|Infinity|NaN|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
_WS = " \t\r\n\f\v\ufeff\u00a0\u2028\u2029"


class _Reader:
    def __init__(self, text: str):
        self.text = text
        self.i = 0
        self.n = len(text)

    def error(self, msg: str) -> JSON5Error:
        line = self.text.count("\n", 0, self.i) + 1
        col = self.i - self.text.rfind("\n", 0, self.i)
        return JSON5Error(f"line {line}, column {col}: {msg}")

    def skip(self) -> None:
        while self.i < self.n:
            c = self.text[self.i]
            if c in _WS or c.isspace():
                self.i += 1
                continue
            if self.text.startswith("//", self.i):
                end = self.text.find("\n", self.i + 2)
                self.i = self.n if end < 0 else end + 1
                continue
            if self.text.startswith("/*", self.i):
                end = self.text.find("*/", self.i + 2)
                if end < 0:
                    raise self.error("unterminated block comment")
                self.i = end + 2
                continue
            break

    def string(self) -> str:
        quote = self.text[self.i]
        self.i += 1
        out: list[str] = []
        escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0", "\\": "\\", "'": "'", '"': '"', "/": "/"}
        while self.i < self.n:
            c = self.text[self.i]
            if c == quote:
                self.i += 1
                return "".join(out)
            if c == "\\":
                self.i += 1
                if self.i >= self.n:
                    raise self.error("unterminated escape")
                e = self.text[self.i]
                if e == "u":
                    raw = self.text[self.i + 1:self.i + 5]
                    if len(raw) != 4:
                        raise self.error("bad unicode escape")
                    try:
                        out.append(chr(int(raw, 16)))
                    except ValueError:
                        raise self.error("bad unicode escape") from None
                    self.i += 5
                    continue
                if e == "x":
                    raw = self.text[self.i + 1:self.i + 3]
                    try:
                        out.append(chr(int(raw, 16)))
                    except ValueError:
                        raise self.error("bad hex escape") from None
                    self.i += 3
                    continue
                if e in "\n\u2028\u2029":
                    self.i += 1
                    continue
                if e == "\r":
                    self.i += 1
                    if self.i < self.n and self.text[self.i] == "\n":
                        self.i += 1
                    continue
                out.append(escapes.get(e, e))
                self.i += 1
                continue
            if c in "\r\n":
                raise self.error("unescaped newline in string")
            out.append(c)
            self.i += 1
        raise self.error("unterminated string")

    def key(self) -> str:
        self.skip()
        if self.i >= self.n:
            raise self.error("expected key")
        if self.text[self.i] in "\"'":
            return self.string()
        m = _IDENT.match(self.text, self.i)
        if not m:
            raise self.error("expected object key")
        self.i = m.end()
        return m.group(0)

    def value(self) -> Any:
        self.skip()
        if self.i >= self.n:
            raise self.error("unexpected end of input")
        c = self.text[self.i]
        if c == "{":
            return self.obj()
        if c == "[":
            return self.arr()
        if c in "\"'":
            return self.string()
        for word, value in (("true", True), ("false", False), ("null", None)):
            if self.text.startswith(word, self.i):
                end = self.i + len(word)
                if end == self.n or not (self.text[end].isalnum() or self.text[end] in "_$"):
                    self.i = end
                    return value
        m = _NUMBER.match(self.text, self.i)
        if not m:
            raise self.error(f"unexpected token {self.text[self.i:self.i+16]!r}")
        raw = m.group(0)
        self.i = m.end()
        sign = -1 if raw.startswith("-") else 1
        body = raw[1:] if raw[:1] in "+-" else raw
        if body == "Infinity":
            return math.inf * sign
        if body == "NaN":
            return math.nan
        if body.lower().startswith("0x"):
            return sign * int(body, 16)
        if any(ch in body for ch in ".eE"):
            return sign * float(body)
        return sign * int(body)

    def obj(self) -> dict[str, Any]:
        self.i += 1
        out: dict[str, Any] = {}
        while True:
            self.skip()
            if self.i >= self.n:
                raise self.error("unterminated object")
            if self.text[self.i] == "}":
                self.i += 1
                return out
            key = self.key()
            self.skip()
            if self.i >= self.n or self.text[self.i] != ":":
                raise self.error(f"expected ':' after {key!r}")
            self.i += 1
            out[key] = self.value()
            self.skip()
            if self.i < self.n and self.text[self.i] == ",":
                self.i += 1

    def arr(self) -> list[Any]:
        self.i += 1
        out: list[Any] = []
        while True:
            self.skip()
            if self.i >= self.n:
                raise self.error("unterminated array")
            if self.text[self.i] == "]":
                self.i += 1
                return out
            out.append(self.value())
            self.skip()
            if self.i < self.n and self.text[self.i] == ",":
                self.i += 1


def loads(text: str) -> Any:
    r = _Reader(text.lstrip("\ufeff"))
    value = r.value()
    r.skip()
    if r.i != r.n:
        raise r.error("trailing data")
    return value


def load(path: Path | str) -> Any:
    p = Path(path)
    try:
        return loads(p.read_text(encoding="utf-8-sig"))
    except JSON5Error as exc:
        raise JSON5Error(f"{p}: {exc}") from None


def _quote(value: str) -> str:
    rep = value.replace("\\", "\\\\").replace('"', '\\"')
    rep = rep.replace("\b", "\\b").replace("\f", "\\f").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f'"{rep}"'


def _key(value: str) -> str:
    return value if _IDENT.fullmatch(value) else _quote(value)


def dumps(value: Any, indent: int = 2, level: int = 0) -> str:
    pad = " " * (indent * level)
    nxt = " " * (indent * (level + 1))
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "-Infinity" if value < 0 else "Infinity"
        if value == 0:
            return "0.0" if math.copysign(1.0, value) > 0 else "-0.0"
        text = repr(value)
        return text
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        for k, v in value.items():
            lines.append(f"{nxt}{_key(str(k))}: {dumps(v, indent, level + 1)},")
        lines.append(pad + "}")
        return "\n".join(lines)
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        # Keep compact primitive arrays readable, but expand nested objects.
        if len(value) <= 4 and all(not isinstance(v, (dict, list, tuple)) for v in value):
            return "[" + ", ".join(dumps(v, indent, level + 1) for v in value) + "]"
        lines = ["["]
        for v in value:
            rendered = dumps(v, indent, level + 1)
            if "\n" in rendered:
                rendered = rendered.replace("\n", "\n" + nxt)
            lines.append(f"{nxt}{rendered},")
        lines.append(pad + "]")
        return "\n".join(lines)
    return _quote(str(value))


def save(path: Path | str, value: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, dumps(value) + "\n")
