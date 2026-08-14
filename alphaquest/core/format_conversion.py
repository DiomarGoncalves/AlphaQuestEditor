from __future__ import annotations

"""FTB Quests storage conversion and language splitting tools.

The module is intentionally standalone so it can also be used by scripts/tests.
It supports the two layouts Alpha Quest Editor targets:

* Minecraft 1.21.1 / FTB Quests 2101.x: SNBT quest files and a flat lang file
  (optionally split by the Quests Lang Splitter addon).
* Minecraft 26.1.2 / FTB Quests 26.1.2.x: JSON5 quest files with native split
  language files.

The conversion is conservative: unknown quest/task/reward fields are preserved
whenever their value can be represented in the destination format.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import copy
import shutil
import time

from . import snbt_codec, json5_codec


@dataclass
class ConversionReport:
    direction: str
    source: Path
    destination: Path
    files_written: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def add(self, relative: Path | str) -> None:
        self.files_written.append(str(relative).replace('\\', '/'))

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)

    def summary(self) -> str:
        lines = [f"{self.direction}: {len(self.files_written)} arquivo(s) gerado(s)"]
        for k, v in sorted(self.stats.items()):
            lines.append(f"{k}: {v}")
        if self.warnings:
            lines.append("")
            lines.append("Avisos:")
            lines.extend(f"- {w}" for w in self.warnings)
        return "\n".join(lines)


def resolve_quest_root(path: Path | str) -> Path:
    root = Path(path)
    candidates = [root / "config" / "ftbquests" / "quests", root / "ftbquests" / "quests", root]
    for c in candidates:
        if (c / "chapters").exists() or (c / "data.snbt").exists() or (c / "data.json5").exists():
            return c
    return candidates[0]


def detect_quest_format(path: Path | str) -> str:
    root = resolve_quest_root(path)
    json_count = len(list((root / "chapters").glob("*.json5"))) if (root / "chapters").exists() else 0
    snbt_count = len(list((root / "chapters").glob("*.snbt"))) if (root / "chapters").exists() else 0
    if json_count and snbt_count: return "mixed"
    if json_count or (root / "data.json5").exists(): return "json5"
    if snbt_count or (root / "data.snbt").exists(): return "snbt"
    return "unknown"


def _load_snbt(path: Path, default: Any) -> Any:
    return snbt_codec.load(path) if path.exists() else copy.deepcopy(default)


def _load_json5(path: Path, default: Any) -> Any:
    return json5_codec.load(path) if path.exists() else copy.deepcopy(default)


def _chapter_owner(chapters: list[tuple[str, dict[str, Any]]]) -> dict[str, str]:
    owner: dict[str, str] = {}
    for stem, ch in chapters:
        for q in ch.get("quests", []) or []:
            if not isinstance(q, dict): continue
            qid = str(q.get("id", ""))
            if qid: owner[qid] = stem
            for bucket in ("tasks", "rewards"):
                for obj in q.get(bucket, []) or []:
                    if isinstance(obj, dict) and obj.get("id"):
                        owner[str(obj["id"])] = stem
        for bucket in ("quest_links", "images"):
            for obj in ch.get(bucket, []) or []:
                if isinstance(obj, dict) and obj.get("id"):
                    owner[str(obj["id"])] = stem
    return owner


def _extract_inline_text(data: dict[str, Any], groups: dict[str, Any], chapters: list[tuple[str, dict[str, Any]]], reward_tables: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Move legacy inline translatable fields into the translation table."""
    out: dict[str, Any] = {}
    if data.get("title"):
        out["file.0000000000000001.title"] = data.pop("title")
    for g in groups.get("chapter_groups", []) or []:
        if isinstance(g, dict) and g.get("id") and g.get("title"):
            out[f"chapter_group.{g['id']}.title"] = g.pop("title")
    for _, table in reward_tables:
        if table.get("id") and table.get("title"):
            out[f"reward_table.{table['id']}.title"] = table.pop("title")
    for _, ch in chapters:
        cid = ch.get("id")
        if cid:
            if ch.get("title"): out[f"chapter.{cid}.title"] = ch.pop("title")
            if ch.get("subtitle"): out[f"chapter.{cid}.chapter_subtitle"] = ch.pop("subtitle")
        for q in ch.get("quests", []) or []:
            if not isinstance(q, dict): continue
            qid = q.get("id")
            if qid:
                mapping = {"title":"title", "subtitle":"quest_subtitle", "description":"quest_desc"}
                for src, dst in mapping.items():
                    if q.get(src) not in (None, "", []): out[f"quest.{qid}.{dst}"] = q.pop(src)
            for kind, bucket in (("task", "tasks"), ("reward", "rewards")):
                for obj in q.get(bucket, []) or []:
                    if isinstance(obj, dict) and obj.get("id") and obj.get("title"):
                        out[f"{kind}.{obj['id']}.title"] = obj.pop("title")
    return out


def _read_flat_or_split_snbt_lang(root: Path) -> dict[str, dict[str, Any]]:
    lang_root = root / "lang"
    locales: dict[str, dict[str, Any]] = {}
    if not lang_root.exists(): return locales
    for p in sorted(lang_root.glob("*.snbt")):
        try:
            data = snbt_codec.load(p)
            if isinstance(data, dict): locales.setdefault(p.stem, {}).update(data)
        except Exception:
            continue
    # Quests Lang Splitter layout: lang/<locale>/**/*.snbt
    for loc_dir in sorted(p for p in lang_root.iterdir() if p.is_dir() and p.name not in ("recovery",)):
        table = locales.setdefault(loc_dir.name, {})
        for p in sorted(loc_dir.rglob("*.snbt")):
            if p.name.endswith(".snbt_merged"): continue
            try:
                data = snbt_codec.load(p)
                if isinstance(data, dict): table.update(data)
            except Exception:
                continue
    return locales


def _read_json5_lang(root: Path) -> dict[str, dict[str, Any]]:
    lang_root = root / "lang"
    locales: dict[str, dict[str, Any]] = {}
    if not lang_root.exists(): return locales
    for loc_dir in sorted(p for p in lang_root.iterdir() if p.is_dir()):
        table: dict[str, Any] = {}
        for p in sorted(loc_dir.rglob("*.json5")):
            try:
                data = json5_codec.load(p)
                if isinstance(data, dict): table.update(data)
            except Exception:
                continue
        locales[loc_dir.name] = table
    return locales


def _split_lang_table(table: dict[str, Any], owner: dict[str, str]) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    type_file = {"file":"file", "chapter":"chapter", "chapter_group":"chapter_group", "reward_table":"reward_table"}
    for key, value in table.items():
        parts = str(key).split(".")
        if len(parts) < 3:
            files.setdefault("misc", {})[str(key)] = value
            continue
        kind, oid = parts[0], parts[1]
        if kind in type_file:
            rel = type_file[kind]
        elif kind in ("quest", "task", "reward", "quest_link", "image"):
            rel = f"chapters/{owner.get(oid, '_orphaned')}"
        else:
            rel = "misc"
        files.setdefault(rel, {})[str(key)] = value
    return files


def _deep_plain(value: Any) -> Any:
    if isinstance(value, dict): return {str(k): _deep_plain(v) for k, v in value.items()}
    if isinstance(value, list): return [_deep_plain(v) for v in value]
    if isinstance(value, tuple): return [_deep_plain(v) for v in value]
    return value


FILE_DEFAULTS_26 = {
    "default_reward_team": False,
    "default_consume_items": False,
    "default_autoclaim_rewards": "disabled",
    "default_quest_shape": "circle",
    "default_quest_disable_jei": False,
    "emergency_items_cooldown": 300,
    "drop_loot_crates": False,
    "disable_gui": False,
    "grid_scale": 0.5,
    "pause_game": False,
    "lock_message": "",
    "progression_mode": "flexible",
    "detection_delay": 20,
    "show_lock_icons": True,
    "drop_book_on_death": False,
    "hide_excluded_quests": False,
    "fallback_locale": "en_us",
    "verify_on_load": False,
}

CHAPTER_ALWAYS_26 = {
    "filename": "",
    "default_quest_shape": "",
    "default_hide_dependency_lines": False,
}


def _normalize_item_stack(value: Any) -> Any:
    """Normalize common legacy ItemStack shapes without touching unknown payloads."""
    if isinstance(value, str):
        return {"id": value, "count": 1}
    if not isinstance(value, dict):
        return value
    out = _deep_plain(copy.deepcopy(value))
    if "id" in out and "count" not in out:
        out["count"] = 1
    return out


def _migrate_26_object(value: Any) -> Any:
    """Small compatibility migrations that are unambiguous between 2101 and 26.1.2."""
    if isinstance(value, list):
        return [_migrate_26_object(v) for v in value]
    if not isinstance(value, dict):
        return value
    out = {str(k): _migrate_26_object(v) for k, v in value.items()}
    for key in ("icon", "item"):
        if key in out:
            out[key] = _normalize_item_stack(out[key])
    # FTB Quests 2101 migrated the old boolean command permission switch to an int.
    if str(out.get("type", "")) == "command" and "elevate_perms" in out and "permission_level" not in out:
        if bool(out.pop("elevate_perms")):
            out["permission_level"] = 2
    return out


def _prepare_json5_data(data: dict[str, Any]) -> dict[str, Any]:
    out = _migrate_26_object(copy.deepcopy(data)) if isinstance(data, dict) else {}
    out.pop("title", None)
    out["version"] = 13
    # The 26.1.2 reader expects these top-level values to exist. We preserve any
    # user-defined value and only fill entries that are missing.
    for key, default in FILE_DEFAULTS_26.items():
        out.setdefault(key, copy.deepcopy(default))
    return out


def _prepare_json5_chapter(ch: dict[str, Any], stem: str) -> dict[str, Any]:
    source = _migrate_26_object(copy.deepcopy(ch)) if isinstance(ch, dict) else {}
    cid = source.pop("id", "")
    group = source.pop("group", "")
    order_index = source.pop("order_index", 0)
    quests = source.pop("quests", []) or []
    links = source.pop("quest_links", []) or []
    images = source.pop("images", []) or []
    for key in ("title", "subtitle", "description"):
        source.pop(key, None)
    for key, default in CHAPTER_ALWAYS_26.items():
        source.setdefault(key, stem if key == "filename" else copy.deepcopy(default))

    normalized_quests = []
    for q in quests:
        if not isinstance(q, dict):
            continue
        q = _migrate_26_object(copy.deepcopy(q))
        qid = q.pop("id", "")
        tasks = q.pop("tasks", None)
        rewards = q.pop("rewards", None)
        for key in ("title", "subtitle", "description"):
            q.pop(key, None)
        q["id"] = qid
        if tasks is not None:
            q["tasks"] = tasks
        if rewards is not None:
            q["rewards"] = rewards
        normalized_quests.append(q)

    out: dict[str, Any] = {
        "id": cid,
        "group": group,
        "order_index": int(order_index or 0),
    }
    out.update(source)
    out["quests"] = normalized_quests
    out["quest_links"] = [_migrate_26_object(v) for v in links if isinstance(v, dict)]
    out["images"] = [_migrate_26_object(v) for v in images if isinstance(v, dict)]
    return out


def _prepare_json5_groups(groups: dict[str, Any]) -> dict[str, Any]:
    out = _migrate_26_object(copy.deepcopy(groups)) if isinstance(groups, dict) else {"chapter_groups": []}
    out.setdefault("chapter_groups", [])
    for group in out.get("chapter_groups", []) or []:
        if isinstance(group, dict):
            group.pop("title", None)
    return out


def _prepare_json5_reward_table(table: dict[str, Any]) -> dict[str, Any]:
    out = _migrate_26_object(copy.deepcopy(table)) if isinstance(table, dict) else {}
    out.pop("title", None)
    out.setdefault("order_index", int(out.get("order_index") or 0))
    return out

def convert_snbt_to_json5(source: Path | str, destination: Path | str, *, overwrite: bool = False) -> ConversionReport:
    src = resolve_quest_root(source)
    dst = Path(destination)
    if dst.exists() and any(dst.iterdir()) and not overwrite:
        raise FileExistsError(f"A pasta de destino não está vazia: {dst}")
    dst.mkdir(parents=True, exist_ok=True)
    report = ConversionReport("SNBT → JSON5", src, dst)

    data = _load_snbt(src / "data.snbt", {})
    groups = _load_snbt(src / "chapter_groups.snbt", {"chapter_groups": []})
    chapters: list[tuple[str, dict[str, Any]]] = []
    for p in sorted((src / "chapters").glob("*.snbt")):
        ch = _load_snbt(p, {})
        if not isinstance(ch, dict): continue
        stem = str(ch.get("filename") or p.stem)
        ch.setdefault("filename", stem)
        chapters.append((stem, ch))
    tables: list[tuple[str, dict[str, Any]]] = []
    for p in sorted((src / "reward_tables").glob("*.snbt")) if (src / "reward_tables").exists() else []:
        value = _load_snbt(p, {})
        if isinstance(value, dict): tables.append((p.stem, value))

    inline = _extract_inline_text(data, groups, chapters, tables)
    owner = _chapter_owner(chapters)
    locales = _read_flat_or_split_snbt_lang(src)
    fallback = str(data.get("fallback_locale") or "en_us")
    if inline:
        locales.setdefault(fallback, {})
        locales[fallback] = {**inline, **locales[fallback]}

    json5_codec.save(dst / "data.json5", _prepare_json5_data(data)); report.add("data.json5")
    json5_codec.save(dst / "chapter_groups.json5", _prepare_json5_groups(groups)); report.add("chapter_groups.json5")
    for stem, ch in chapters:
        json5_codec.save(dst / "chapters" / f"{stem}.json5", _prepare_json5_chapter(ch, stem)); report.add(f"chapters/{stem}.json5")
    for stem, table in tables:
        json5_codec.save(dst / "reward_tables" / f"{stem}.json5", _prepare_json5_reward_table(table)); report.add(f"reward_tables/{stem}.json5")

    for locale, table in sorted(locales.items()):
        for rel, values in _split_lang_table(table, owner).items():
            target = dst / "lang" / locale / (rel + ".json5")
            json5_codec.save(target, _deep_plain(values)); report.add(target.relative_to(dst))

    report.stats.update({"chapters": len(chapters), "locales": len(locales), "translations": sum(len(v) for v in locales.values())})
    report.warn("Conversão de storage concluída. Sempre teste a cópia convertida no FTB Quests 26.1.2 antes de substituir seu projeto original.")
    return report


def _merge_json5_locale(root: Path, locale: str) -> dict[str, Any]:
    loc = root / "lang" / locale
    table: dict[str, Any] = {}
    if not loc.exists(): return table
    for p in sorted(loc.rglob("*.json5")):
        try:
            data = json5_codec.load(p)
            if isinstance(data, dict): table.update(data)
        except Exception:
            continue
    return table


def convert_json5_to_snbt(source: Path | str, destination: Path | str, *, overwrite: bool = False, split_lang: bool = False) -> ConversionReport:
    src = resolve_quest_root(source)
    dst = Path(destination)
    if dst.exists() and any(dst.iterdir()) and not overwrite:
        raise FileExistsError(f"A pasta de destino não está vazia: {dst}")
    dst.mkdir(parents=True, exist_ok=True)
    report = ConversionReport("JSON5 → SNBT", src, dst)

    data = _load_json5(src / "data.json5", {})
    if isinstance(data, dict): data["version"] = 13
    groups = _load_json5(src / "chapter_groups.json5", {"chapter_groups": []})
    snbt_codec.save(dst / "data.snbt", data); report.add("data.snbt")
    snbt_codec.save(dst / "chapter_groups.snbt", groups); report.add("chapter_groups.snbt")

    chapters: list[tuple[str, dict[str, Any]]] = []
    for p in sorted((src / "chapters").glob("*.json5")):
        ch = _load_json5(p, {})
        if not isinstance(ch, dict): continue
        stem = str(ch.get("filename") or p.stem)
        ch.setdefault("filename", stem)
        chapters.append((stem, ch))
        snbt_codec.save(dst / "chapters" / f"{stem}.snbt", ch); report.add(f"chapters/{stem}.snbt")
    if (src / "reward_tables").exists():
        for p in sorted((src / "reward_tables").glob("*.json5")):
            table = _load_json5(p, {})
            snbt_codec.save(dst / "reward_tables" / f"{p.stem}.snbt", table); report.add(f"reward_tables/{p.stem}.snbt")

    lang_root = src / "lang"
    locales = sorted(p.name for p in lang_root.iterdir() if p.is_dir()) if lang_root.exists() else []
    owner = _chapter_owner(chapters)
    for locale in locales:
        table = _merge_json5_locale(src, locale)
        if split_lang:
            for rel, values in _split_lang_table(table, owner).items():
                target = dst / "lang" / locale / (rel + ".snbt")
                snbt_codec.save(target, values); report.add(target.relative_to(dst))
        else:
            target = dst / "lang" / f"{locale}.snbt"
            snbt_codec.save(target, table); report.add(target.relative_to(dst))

    report.stats.update({"chapters": len(chapters), "locales": len(locales), "translations": sum(len(_merge_json5_locale(src, l)) for l in locales)})
    report.warn("Ao portar de 26.1.2 para 1.21.1, propriedades exclusivas da versão nova podem ser ignoradas pelo FTB Quests antigo. Revise o relatório/validador após abrir o projeto.")
    return report


def split_snbt_languages(source: Path | str, *, locales: list[str] | None = None, keep_flat: bool = True) -> ConversionReport:
    root = resolve_quest_root(source)
    report = ConversionReport("Lang Splitter", root, root)
    chapters: list[tuple[str, dict[str, Any]]] = []
    for p in sorted((root / "chapters").glob("*.snbt")):
        ch = _load_snbt(p, {})
        if isinstance(ch, dict): chapters.append((str(ch.get("filename") or p.stem), ch))
    owner = _chapter_owner(chapters)
    candidates = sorted((root / "lang").glob("*.snbt")) if (root / "lang").exists() else []
    wanted = set(locales or [])
    for p in candidates:
        if wanted and p.stem not in wanted: continue
        table = _load_snbt(p, {})
        if not isinstance(table, dict): continue
        for rel, values in _split_lang_table(table, owner).items():
            target = root / "lang" / p.stem / (rel + ".snbt")
            snbt_codec.save(target, values); report.add(target.relative_to(root))
        if not keep_flat:
            backup = root / ".alphaquest" / "lang_flat_backup"
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, backup / p.name)
            p.unlink()
        report.stats[p.stem] = len(table)
    return report


def merge_snbt_languages(source: Path | str, *, locales: list[str] | None = None) -> ConversionReport:
    root = resolve_quest_root(source)
    report = ConversionReport("Merge Lang Splitter", root, root)
    lang_root = root / "lang"
    wanted = set(locales or [])
    for loc_dir in sorted(p for p in lang_root.iterdir() if p.is_dir() and p.name != "recovery") if lang_root.exists() else []:
        if wanted and loc_dir.name not in wanted: continue
        table: dict[str, Any] = {}
        for p in sorted(loc_dir.rglob("*.snbt")):
            if p.name.endswith(".snbt_merged"): continue
            try:
                data = snbt_codec.load(p)
                if isinstance(data, dict): table.update(data)
            except Exception:
                continue
        target = lang_root / f"{loc_dir.name}.snbt"
        snbt_codec.save(target, table); report.add(target.relative_to(root)); report.stats[loc_dir.name] = len(table)
    return report


def fill_missing_snbt_translations(
    source: Path | str,
    *,
    target_locale: str,
    source_locale: str = "en_us",
    keep_flat: bool = True,
) -> ConversionReport:
    """Fill missing target strings from a fallback locale, then split target files.

    This mirrors the translator-oriented workflow of Quests Lang Splitter without
    requiring Minecraft to be running. Existing non-empty target strings win.
    """
    root = resolve_quest_root(source)
    report = ConversionReport("Preencher traduções ausentes", root, root)
    target_locale = str(target_locale or "").strip()
    source_locale = str(source_locale or "en_us").strip() or "en_us"
    if not target_locale:
        raise ValueError("Informe o locale de destino, por exemplo pt_br.")
    if target_locale == source_locale:
        raise ValueError("Locale de origem e destino precisam ser diferentes.")

    tables = _read_flat_or_split_snbt_lang(root)
    fallback = tables.get(source_locale)
    if not fallback:
        raise ValueError(f"Locale de origem não encontrado ou vazio: {source_locale}")
    target = dict(tables.get(target_locale, {}))
    added = 0
    for key, value in fallback.items():
        current = target.get(key)
        if current in (None, "", []):
            target[key] = copy.deepcopy(value)
            added += 1

    lang_root = root / "lang"
    lang_root.mkdir(parents=True, exist_ok=True)
    flat = lang_root / f"{target_locale}.snbt"
    snbt_codec.save(flat, target)
    report.add(flat.relative_to(root))
    report.stats["adicionadas"] = added
    report.stats["total_destino"] = len(target)

    split = split_snbt_languages(root, locales=[target_locale], keep_flat=keep_flat)
    for name in split.files_written:
        if name not in report.files_written:
            report.files_written.append(name)
    return report


def purge_merged_snbt_languages(source: Path | str, *, locales: list[str] | None = None) -> ConversionReport:
    """Remove stale ``*.snbt_merged`` files left by Lang Splitter workflows."""
    root = resolve_quest_root(source)
    report = ConversionReport("Limpar .snbt_merged", root, root)
    lang_root = root / "lang"
    wanted = set(locales or [])
    removed = 0
    if lang_root.exists():
        for loc_dir in sorted(p for p in lang_root.iterdir() if p.is_dir() and p.name != "recovery"):
            if wanted and loc_dir.name not in wanted:
                continue
            for path in sorted(loc_dir.rglob("*.snbt_merged")):
                try:
                    rel = path.relative_to(root)
                    path.unlink()
                    report.add(rel)
                    removed += 1
                except OSError as exc:
                    report.warn(f"Não foi possível remover {path}: {exc}")
    report.stats["removidos"] = removed
    return report


def make_backup(source: Path | str) -> Path:
    root = resolve_quest_root(source)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    target = root.parent / f"{root.name}_backup_{stamp}"
    shutil.copytree(root, target)
    return target
