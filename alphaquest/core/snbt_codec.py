from __future__ import annotations

"""General SNBT reader/writer with support for FTB Quests' comma-less dialect."""

import re
from pathlib import Path

from .io_utils import atomic_write_text
from typing import Any


class SNBTError(ValueError):
    pass


_NUM = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([bBsSlLfFdD]?)$")
_INT = re.compile(r"^[+-]?\d+$")
_KEY = re.compile(r"[A-Za-z0-9_./+\-]+")


class _Parser:
    def __init__(self, text: str):
        self.s = text
        self.i = 0
        self.n = len(text)

    def fail(self, msg: str) -> SNBTError:
        line = self.s.count("\n", 0, self.i) + 1
        col = self.i - self.s.rfind("\n", 0, self.i)
        return SNBTError(f"line {line}, column {col}: {msg}")

    def skip(self) -> None:
        while self.i < self.n:
            if self.s[self.i].isspace() or self.s[self.i] in ",;":
                self.i += 1
                continue
            if self.s.startswith("//", self.i):
                end = self.s.find("\n", self.i + 2)
                self.i = self.n if end < 0 else end + 1
                continue
            if self.s[self.i] == "#":
                end = self.s.find("\n", self.i + 1)
                self.i = self.n if end < 0 else end + 1
                continue
            break

    def string(self) -> str:
        quote = self.s[self.i]
        self.i += 1
        out: list[str] = []
        while self.i < self.n:
            c = self.s[self.i]
            if c == quote:
                self.i += 1
                return "".join(out)
            if c == "\\":
                self.i += 1
                if self.i >= self.n:
                    raise self.fail("unterminated string")
                e = self.s[self.i]
                out.append({"n":"\n","r":"\r","t":"\t","\\":"\\",'"':'"',"'":"'"}.get(e, e))
                self.i += 1
                continue
            out.append(c)
            self.i += 1
        raise self.fail("unterminated string")

    def bare(self) -> str:
        start = self.i
        while self.i < self.n:
            c = self.s[self.i]
            if c.isspace() or c in ",;:{}[]":
                break
            if c == "#" or self.s.startswith("//", self.i):
                break
            self.i += 1
        if self.i == start:
            raise self.fail("expected value")
        return self.s[start:self.i]

    def scalar(self, raw: str) -> Any:
        low = raw.lower()
        if low == "true": return True
        if low == "false": return False
        m = _NUM.match(raw)
        if m:
            suffix = (m.group(1) or "").lower()
            body = raw[:-1] if suffix else raw
            try:
                if suffix in ("f", "d") or "." in body or "e" in body.lower():
                    return float(body)
                return int(body)
            except ValueError:
                pass
        if _INT.match(raw):
            try: return int(raw)
            except ValueError: pass
        return raw

    def key(self) -> str:
        self.skip()
        if self.i >= self.n:
            raise self.fail("expected key")
        if self.s[self.i] in "\"'":
            return self.string()
        m = _KEY.match(self.s, self.i)
        if not m:
            raise self.fail("expected key")
        self.i = m.end()
        return m.group(0)

    def compound(self) -> dict[str, Any]:
        if self.s[self.i] != "{": raise self.fail("expected '{'")
        self.i += 1
        out: dict[str, Any] = {}
        while True:
            self.skip()
            if self.i >= self.n: raise self.fail("unterminated compound")
            if self.s[self.i] == "}":
                self.i += 1
                return out
            key = self.key()
            self.skip()
            if self.i >= self.n or self.s[self.i] != ":":
                raise self.fail(f"expected ':' after {key!r}")
            self.i += 1
            out[key] = self.value()

    def array(self) -> list[Any]:
        if self.s[self.i] != "[": raise self.fail("expected '['")
        self.i += 1
        self.skip()
        # Typed array marker: [B; ...], [I; ...], [L; ...]
        if self.i + 1 < self.n and self.s[self.i] in "BILbil" and self.s[self.i + 1] == ";":
            self.i += 2
        out: list[Any] = []
        while True:
            self.skip()
            if self.i >= self.n: raise self.fail("unterminated list")
            if self.s[self.i] == "]":
                self.i += 1
                return out
            out.append(self.value())

    def value(self) -> Any:
        self.skip()
        if self.i >= self.n: raise self.fail("unexpected end")
        c = self.s[self.i]
        if c == "{": return self.compound()
        if c == "[": return self.array()
        if c in "\"'": return self.string()
        return self.scalar(self.bare())

    def parse(self) -> Any:
        value = self.value()
        self.skip()
        if self.i < self.n:
            raise self.fail("trailing data")
        return value


def loads(text: str) -> Any:
    return _Parser(text.lstrip("\ufeff")).parse()


def load(path: Path | str) -> Any:
    p = Path(path)
    try:
        return loads(p.read_text(encoding="utf-8-sig"))
    except SNBTError as exc:
        raise SNBTError(f"{p}: {exc}") from None


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + '"'


def _safe_key(k: str) -> str:
    return k if _KEY.fullmatch(k) else _quote(k)


def dumps(value: Any, level: int = 0, indent: str = "\t") -> str:
    pad = indent * level
    nxt = indent * (level + 1)
    if value is True: return "true"
    if value is False: return "false"
    if value is None: return '""'
    if isinstance(value, str): return _quote(value)
    if isinstance(value, int) and not isinstance(value, bool): return str(value)
    if isinstance(value, float):
        text = f"{value:.12g}"
        # Doubles are the most compatible numeric representation for FTB coords/sizes.
        return text + "d"
    if isinstance(value, dict):
        if not value: return "{ }"
        lines = ["{"]
        for k, v in value.items():
            rendered = dumps(v, level + 1, indent)
            lines.append(f"{nxt}{_safe_key(str(k))}: {rendered}")
        lines.append(pad + "}")
        return "\n".join(lines)
    if isinstance(value, (list, tuple)):
        if not value: return "[ ]"
        if all(not isinstance(v, (dict, list, tuple)) for v in value) and len(value) <= 6:
            return "[ " + " ".join(dumps(v, level + 1, indent) for v in value) + " ]"
        lines = ["["]
        for v in value:
            rendered = dumps(v, level + 1, indent)
            lines.append(nxt + rendered.replace("\n", "\n" + nxt))
        lines.append(pad + "]")
        return "\n".join(lines)
    return _quote(str(value))


def save(path: Path | str, value: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, dumps(value) + "\n")
