from __future__ import annotations

import csv
import json
import io
from pathlib import Path

from .io_utils import atomic_write_text
from typing import Iterable


REPORT_COLUMNS = ["key", "tipo", "contexto", "id_referencia", "pt_br", "en_us", "status"]


def _classify_key(book, key: str) -> tuple[str, str, str]:
    """Return (kind, context, reference_id) for a FTB Quests language key."""
    parts = key.split(".")
    if key.startswith("quest.") and len(parts) >= 3:
        qid = parts[1]
        q = getattr(book, "quest_by_id", {}).get(qid)
        context = ""
        if q is not None:
            context = (getattr(q, "title", "") or getattr(book, "lang_pt", {}).get(f"quest.{qid}.title", "")
                       or getattr(book, "lang_en", {}).get(f"quest.{qid}.title", ""))
        tail = ".".join(parts[2:])
        if tail == "title":
            kind = "Quest - Título"
        elif tail in ("quest_desc", "description"):
            kind = "Quest - Descrição"
        elif ".task." in key or tail.startswith("task."):
            kind = "Task - Texto"
        elif ".reward." in key or tail.startswith("reward."):
            kind = "Reward - Texto"
        else:
            kind = "Quest - Outro"
        return kind, context, qid

    if key.startswith(("task.", "reward.")) and len(parts) >= 3:
        oid = parts[1]
        kind_prefix = "Task" if parts[0] == "task" else "Reward"
        owner = None
        for q in getattr(book, "quest_by_id", {}).values():
            bucket = q.tasks if parts[0] == "task" else q.rewards
            if any(getattr(x, "task_id" if parts[0] == "task" else "reward_id", "") == oid for x in bucket):
                owner = q; break
        context = getattr(owner, "title", "") if owner is not None else ""
        return f"{kind_prefix} - Título", context, oid

    if key.startswith("file.") and len(parts) >= 3:
        return "Quest Book - Título", "Quest Book", parts[1]

    if key.startswith("reward_table.") and len(parts) >= 3:
        return "Reward Table - Título", "", parts[1]

    if key.startswith("chapter_group.") and len(parts) >= 3:
        gid = parts[1]
        g = getattr(book, "group_by_id", {}).get(gid)
        context = getattr(g, "title", "") if g is not None else ""
        return "Grupo - Título", context, gid

    if key.startswith("chapter.") and len(parts) >= 3:
        cid = parts[1]
        ch = next((c for c in getattr(book, "chapters", []) if getattr(c, "chapter_id", "") == cid), None)
        context = getattr(ch, "title", "") if ch is not None else ""
        tail = ".".join(parts[2:])
        kind = "Capítulo - Descrição" if tail in ("chapter_subtitle", "description") else "Capítulo - Título" if tail == "title" else "Capítulo - Outro"
        return kind, context, cid

    return "Outro", "", ""


def translation_status(pt: str, en: str) -> str:
    pt_ok = bool((pt or "").strip())
    en_ok = bool((en or "").strip())
    if pt_ok and en_ok:
        return "OK"
    if not pt_ok and not en_ok:
        return "FALTA_PT_BR_E_EN_US"
    if not pt_ok:
        return "FALTA_PT_BR"
    return "FALTA_EN_US"


def collect_translation_rows(book, keys: Iterable[str] | None = None) -> list[dict[str, str]]:
    all_keys = set(getattr(book, "lang_pt", {})) | set(getattr(book, "lang_en", {}))
    # Include keys that are structurally expected even when both language files are incomplete.
    for ch in getattr(book, "chapters", []):
        if getattr(ch, "title_key", ""):
            all_keys.add(ch.title_key)
        for q in getattr(ch, "quests", []):
            if getattr(q, "title_key", ""):
                all_keys.add(q.title_key)
            if getattr(q, "description_key", ""):
                all_keys.add(q.description_key)
    if keys is not None:
        wanted = set(keys)
        all_keys &= wanted

    rows: list[dict[str, str]] = []
    for key in sorted(all_keys):
        if not key.startswith(("quest.", "task.", "reward.", "quest_link.", "image.", "chapter.", "chapter_group.", "file.", "reward_table.")):
            continue
        pt = getattr(book, "lang_pt", {}).get(key, "")
        en = getattr(book, "lang_en", {}).get(key, "")
        kind, context, ref_id = _classify_key(book, key)
        rows.append({
            "key": key,
            "tipo": kind,
            "contexto": context,
            "id_referencia": ref_id,
            "pt_br": pt,
            "en_us": en,
            "status": translation_status(pt, en),
        })
    return rows


def export_translation_report(book, path: Path, keys: Iterable[str] | None = None) -> int:
    """Export a translator/AI-friendly report as CSV or JSON.

    CSV uses UTF-8 BOM + semicolon, which opens cleanly in common pt-BR Excel setups
    while remaining plain text for AI tools. Newlines inside descriptions are quoted
    by the csv module and round-trip correctly.
    """
    rows = collect_translation_rows(book, keys)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        atomic_write_text(path, json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=REPORT_COLUMNS, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            writer.writerows(rows)
    return len(rows)


def _normalize_record(row: dict) -> dict[str, str] | None:
    aliases = {
        "chave": "key", "key": "key",
        "português (pt_br)": "pt_br", "portugues (pt_br)": "pt_br", "português": "pt_br", "portugues": "pt_br", "pt": "pt_br", "pt_br": "pt_br",
        "english (en_us)": "en_us", "english": "en_us", "inglês": "en_us", "ingles": "en_us", "en": "en_us", "en_us": "en_us",
    }
    out = {"key": "", "pt_br": "", "en_us": ""}
    provided = set()
    for raw_k, raw_v in row.items():
        k = str(raw_k or "").strip().casefold()
        target = aliases.get(k)
        if target:
            out[target] = "" if raw_v is None else str(raw_v).replace("\r\n", "\n").replace("\r", "\n")
            provided.add(target)
    key = out["key"].strip()
    if not key or not key.startswith(("quest.", "task.", "reward.", "quest_link.", "image.", "chapter.", "chapter_group.", "file.", "reward_table.")):
        return None
    out["key"] = key
    # Distinguish a missing column from an intentionally/accidentally blank cell.
    # The importer preserves existing translations when the value is blank, so this
    # mainly exists for future compatibility and clear behavior in tests.
    out["_provided"] = ",".join(sorted(provided))
    return out


def import_translation_report(path: Path) -> list[dict[str, str]]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            raw = raw.get("rows") or raw.get("translations") or []
        if not isinstance(raw, list):
            raise ValueError("O JSON precisa conter uma lista de traduções.")
        rows = [r for r in (_normalize_record(x) for x in raw if isinstance(x, dict)) if r]
        return rows

    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        return []
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=";,\t,")
        reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)
    except csv.Error:
        # Alpha Quest Editor exports semicolon CSV by default.
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=";")
    return [r for r in (_normalize_record(x) for x in reader) if r]
