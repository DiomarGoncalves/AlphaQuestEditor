from __future__ import annotations

"""Crowdin-style translation import and QA helpers.

The module deliberately stays independent from Qt so the same checks can be used by
CLI/build tests later.  It supports the language formats used by Alpha Quest Editor:
legacy/split SNBT and native JSON5.
"""

from collections import Counter
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
import re
from typing import Iterable

from .json5_codec import loads as loads_json5, JSON5Error
from .snbt_codec import loads as loads_snbt, SNBTError
from .lang import discover_locales, load_locale_tree

KEY_PREFIXES = (
    "quest.", "task.", "reward.", "quest_link.", "image.",
    "chapter.", "chapter_group.", "file.", "reward_table.",
)


@dataclass
class TranslationIssue:
    severity: str  # error | warning | info
    code: str
    message: str
    line: int = 0
    column: int = 0
    key: str = ""
    file: str = ""

    def label(self) -> str:
        where = ""
        if self.line:
            where = f"linha {self.line}" + (f", col. {self.column}" if self.column else "")
        return f"{where}: {self.message}" if where else self.message


@dataclass
class ImportRow:
    key: str
    imported: str
    current: str = ""
    source: str = ""
    status: str = "ALTERADA"  # ALTERADA | NOVA | IGUAL | CHAVE_DESCONHECIDA
    line: int = 0
    issues: list[TranslationIssue] = field(default_factory=list)

    @property
    def has_error(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def qa_text(self) -> str:
        return " • ".join(i.message for i in self.issues)


@dataclass
class TranslationImportAnalysis:
    path: Path
    target_locale: str
    source_locale: str
    rows: list[ImportRow] = field(default_factory=list)
    issues: list[TranslationIssue] = field(default_factory=list)
    source_format: str = ""

    @property
    def errors(self) -> int:
        return sum(i.severity == "error" for i in self.issues) + sum(r.has_error for r in self.rows)

    @property
    def warnings(self) -> int:
        return sum(i.severity == "warning" for i in self.issues) + sum(
            sum(i.severity == "warning" for i in r.issues) for r in self.rows
        )


def _flatten(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def guess_locale_from_path(path: Path | str) -> str:
    """Best-effort locale detection for files exported by translators/Crowdin."""
    p = Path(path)
    candidates = [p.stem.casefold()] + [part.casefold() for part in p.parts]
    locale_re = re.compile(r"^[a-z]{2,3}[_-][a-z]{2,4}$", re.I)
    for value in reversed(candidates):
        clean = value.replace("-", "_")
        if locale_re.fullmatch(clean):
            return clean.lower()
        # Typical names such as pt_br.snbt, lang_pt_br.json5 or quests-pt_br.json5.
        m = re.search(r"(?:^|[_\-.])([a-z]{2,3}[_-][a-z]{2,4})(?:$|[_\-.])", value, re.I)
        if m:
            return m.group(1).replace("-", "_").lower()
    return ""


def _line_col_from_error(message: str) -> tuple[int, int]:
    m = re.search(r"line\s+(\d+),\s*column\s+(\d+)", message, re.I)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _scan_key_lines_and_duplicates(text: str) -> tuple[dict[str, int], list[TranslationIssue]]:
    # Language keys normally live one per entry. This scanner is intentionally
    # permissive so it can still report duplicate keys before/after list values.
    rx = re.compile(r'''(?m)^\s*(?:"([^"\r\n]+)"|'([^'\r\n]+)'|([A-Za-z0-9_./+\-]+))\s*:''')
    lines: dict[str, int] = {}
    issues: list[TranslationIssue] = []
    for m in rx.finditer(text):
        key = next((g for g in m.groups() if g is not None), "")
        line = text.count("\n", 0, m.start()) + 1
        if key in lines:
            issues.append(TranslationIssue(
                "error", "DUPLICATE_KEY",
                f"Chave duplicada; primeira ocorrência na linha {lines[key]}.",
                line=line, key=key,
            ))
        else:
            lines[key] = line
    return lines, issues


def _scan_raw_newlines_inside_quotes(text: str) -> list[TranslationIssue]:
    """Flag physical line breaks inside quoted strings.

    JSON5 rejects them. The permissive FTB-style SNBT reader may accept them in a
    few contexts, but for language files they are almost always an accidental
    broken string; multiline translations should use escaped \n or a list.
    """
    issues: list[TranslationIssue] = []
    quote = ""
    escaped = False
    line = 1
    start_line = 0
    i = 0
    while i < len(text):
        c = text[i]
        if not quote:
            if text.startswith("//", i):
                j = text.find("\n", i + 2)
                if j < 0:
                    break
                i = j
                continue
            if c == "#":
                j = text.find("\n", i + 1)
                if j < 0:
                    break
                i = j
                continue
            if c in ('"', "'"):
                quote = c
                start_line = line
        else:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == quote:
                quote = ""
            elif c in "\r\n":
                issues.append(TranslationIssue(
                    "error", "RAW_NEWLINE_IN_STRING",
                    f"String iniciada na linha {start_line} foi quebrada por uma nova linha física. Use \\n ou uma lista de strings.",
                    line=line,
                ))
                # Report one issue per broken string; keep scanning until closing quote.
        if c == "\n":
            line += 1
        i += 1
    if quote:
        issues.append(TranslationIssue(
            "error", "UNTERMINATED_STRING",
            f"String iniciada na linha {start_line} não foi fechada.", line=start_line,
        ))
    # De-duplicate raw-newline spam for the same start line.
    dedup: dict[tuple[str, int], TranslationIssue] = {}
    for issue in issues:
        dedup.setdefault((issue.code, issue.line), issue)
    return list(dedup.values())


def _parse_translation_text(path: Path) -> tuple[dict[str, str], str, dict[str, int], list[TranslationIssue]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    key_lines, issues = _scan_key_lines_and_duplicates(text)
    issues.extend(_scan_raw_newlines_inside_quotes(text))
    suffix = path.suffix.lower()
    try:
        if suffix in (".json5", ".json"):
            raw = loads_json5(text)
            fmt = "json5"
        else:
            raw = loads_snbt(text)
            fmt = "snbt"
    except (SNBTError, JSON5Error) as exc:
        line, col = _line_col_from_error(str(exc))
        issues.append(TranslationIssue("error", "SYNTAX", str(exc), line=line, column=col, file=str(path)))
        return {}, "json5" if suffix in (".json5", ".json") else "snbt", key_lines, issues
    except Exception as exc:
        issues.append(TranslationIssue("error", "SYNTAX", str(exc), file=str(path)))
        return {}, "", key_lines, issues
    if not isinstance(raw, dict):
        issues.append(TranslationIssue("error", "ROOT_NOT_OBJECT", "O arquivo de tradução precisa ter um objeto/compound na raiz.", file=str(path)))
        return {}, fmt, key_lines, issues
    return {str(k): _flatten(v) for k, v in raw.items()}, fmt, key_lines, issues


_PLACEHOLDER_RE = re.compile(
    r"%(?:\d+\$)?[sdif]|%\d+|\$\{[^{}]+\}|\{[A-Za-z_][A-Za-z0-9_.:-]*\}|§[0-9A-FK-ORa-fk-or]"
)
_NUMBER_RE = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?%?(?![\w.])")
_TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9:_-]*)\b[^>]*>")


def _counter(pattern: re.Pattern, value: str, *, normalize_numbers: bool = False) -> Counter:
    vals = pattern.findall(value or "")
    if pattern is _TAG_RE:
        vals = [str(v).lower() for v in vals]
    if normalize_numbers:
        vals = [str(v).replace(",", ".") for v in vals]
    return Counter(vals)


def _qa_for_value(key: str, source: str, target: str, line: int = 0) -> list[TranslationIssue]:
    issues: list[TranslationIssue] = []
    if not target.strip():
        issues.append(TranslationIssue("warning", "EMPTY", "Tradução vazia.", line=line, key=key))
        return issues
    if source:
        src_ph, dst_ph = _counter(_PLACEHOLDER_RE, source), _counter(_PLACEHOLDER_RE, target)
        if src_ph != dst_ph:
            issues.append(TranslationIssue(
                "error", "PLACEHOLDER_MISMATCH",
                f"Placeholders/códigos não conferem com a origem ({dict(src_ph)} → {dict(dst_ph)}).",
                line=line, key=key,
            ))
        src_tags, dst_tags = _counter(_TAG_RE, source), _counter(_TAG_RE, target)
        if src_tags != dst_tags:
            issues.append(TranslationIssue(
                "warning", "TAG_MISMATCH",
                f"Tags diferem da origem ({dict(src_tags)} → {dict(dst_tags)}).",
                line=line, key=key,
            ))
        src_num, dst_num = _counter(_NUMBER_RE, source, normalize_numbers=True), _counter(_NUMBER_RE, target, normalize_numbers=True)
        if src_num != dst_num:
            issues.append(TranslationIssue(
                "warning", "NUMBER_MISMATCH",
                f"Números/percentuais diferem da origem ({dict(src_num)} → {dict(dst_num)}).",
                line=line, key=key,
            ))
        if source.count("\n") != target.count("\n"):
            issues.append(TranslationIssue(
                "warning", "LINEBREAK_MISMATCH",
                f"Quantidade de quebras de linha mudou ({source.count(chr(10))} → {target.count(chr(10))}).",
                line=line, key=key,
            ))
    return issues


def _known_project_keys(book) -> set[str]:
    known = set(getattr(book, "lang_pt", {})) | set(getattr(book, "lang_en", {}))
    for ch in getattr(book, "chapters", []):
        if getattr(ch, "title_key", ""):
            known.add(ch.title_key)
        for q in getattr(ch, "quests", []):
            if getattr(q, "title_key", ""):
                known.add(q.title_key)
            if getattr(q, "description_key", ""):
                known.add(q.description_key)
            for t in getattr(q, "tasks", []):
                if getattr(t, "task_id", ""):
                    known.add(f"task.{t.task_id}.title")
                    known.add(f"quest.{q.quest_id}.task.{t.task_id}.title")
            for r in getattr(q, "rewards", []):
                if getattr(r, "reward_id", ""):
                    known.add(f"reward.{r.reward_id}.title")
                    known.add(f"quest.{q.quest_id}.reward.{r.reward_id}.title")
    return known


def analyze_translation_file(book, path: Path | str, target_locale: str, source_locale: str = "en_us") -> TranslationImportAnalysis:
    path = Path(path)
    target_locale = (target_locale or guess_locale_from_path(path) or "pt_br").replace("-", "_").lower()
    source_locale = (source_locale or "en_us").replace("-", "_").lower()
    entries, fmt, line_map, issues = _parse_translation_text(path)
    analysis = TranslationImportAnalysis(path=path, target_locale=target_locale, source_locale=source_locale, issues=issues, source_format=fmt)
    if any(i.severity == "error" and i.code == "SYNTAX" for i in issues):
        return analysis

    current = load_locale_tree(book.quest_root, target_locale, book.storage_format)
    source = load_locale_tree(book.quest_root, source_locale, book.storage_format)
    known = _known_project_keys(book) | set(source) | set(current)
    known_list = sorted(known)
    for key, value in entries.items():
        line = line_map.get(key, 0)
        old = current.get(key, "")
        row_issues: list[TranslationIssue] = []
        if not key.startswith(KEY_PREFIXES):
            row_issues.append(TranslationIssue("warning", "UNKNOWN_NAMESPACE", "Chave não parece pertencer ao FTB Quests.", line=line, key=key))
        unknown = key not in known
        if unknown:
            close = get_close_matches(key, known_list, n=1, cutoff=0.78)
            hint = f" Possível chave: {close[0]}" if close else ""
            row_issues.append(TranslationIssue(
                "error", "UNKNOWN_KEY",
                "Chave não existe no Quest Book atual." + hint,
                line=line, key=key,
            ))
        row_issues.extend(_qa_for_value(key, source.get(key, ""), value, line))
        status = "CHAVE_DESCONHECIDA" if unknown else ("IGUAL" if value == old else ("NOVA" if key not in current else "ALTERADA"))
        analysis.rows.append(ImportRow(key, value, old, source.get(key, ""), status, line, row_issues))
    return analysis


def validate_locale_files(book, locale: str) -> list[TranslationIssue]:
    """Validate all physical language files used by one locale and return exact lines."""
    locale = (locale or "pt_br").replace("-", "_").lower()
    lang_root = Path(book.quest_root) / "lang"
    files: list[Path] = []
    if book.storage_format == "json5":
        loc = lang_root / locale
        if loc.exists():
            files.extend(sorted(loc.rglob("*.json5")))
    else:
        flat = lang_root / f"{locale}.snbt"
        if flat.exists():
            files.append(flat)
        loc = lang_root / locale
        if loc.exists():
            files.extend(sorted(p for p in loc.rglob("*.snbt") if not p.name.endswith(".snbt_merged")))

    all_issues: list[TranslationIssue] = []
    source_locale = "en_us" if locale != "en_us" else "pt_br"
    source = load_locale_tree(book.quest_root, source_locale, book.storage_format)
    known = _known_project_keys(book) | set(source)
    for path in files:
        entries, _, line_map, issues = _parse_translation_text(path)
        for issue in issues:
            issue.file = str(path)
        all_issues.extend(issues)
        for key, value in entries.items():
            line = line_map.get(key, 0)
            if key not in known:
                close = get_close_matches(key, sorted(known), n=1, cutoff=0.78)
                hint = f" Possível chave: {close[0]}" if close else ""
                all_issues.append(TranslationIssue("warning", "UNKNOWN_KEY", "Chave não encontrada na estrutura atual." + hint, line=line, key=key, file=str(path)))
            for issue in _qa_for_value(key, source.get(key, ""), value, line):
                issue.file = str(path)
                all_issues.append(issue)
    return all_issues


def available_locales(book) -> list[str]:
    found = set(discover_locales(book.quest_root, book.storage_format))
    found.update(("pt_br", "en_us"))
    return sorted(found)
