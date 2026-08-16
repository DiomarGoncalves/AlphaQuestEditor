from __future__ import annotations

"""FTB Quests 1.20.x <-> 1.21.x SNBT porting helpers.

FTB Quests 1.20.x stored user-facing text inline in the quest SNBT.  The
1.21.x line moved translatable text to ``lang/<locale>.snbt`` while keeping
quest structure in SNBT.  This module performs that text migration offline
without launching Minecraft.

The port is intentionally conservative.  Unknown fields and complex item
payloads are copied verbatim; custom legacy item NBT is reported for manual
review because Minecraft 1.21 item components are not a lossless mechanical
mapping for arbitrary 1.20 custom NBT.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import copy
import shutil

from . import snbt_codec
from .format_conversion import resolve_quest_root


@dataclass
class LegacyPortAnalysis:
    source: Path
    direction: str
    locale: str = "en_us"
    inline_strings: int = 0
    external_strings: int = 0
    conflicts: int = 0
    chapters: int = 0
    quests: int = 0
    tasks: int = 0
    rewards: int = 0
    quest_links: int = 0
    groups: int = 0
    reward_tables: int = 0
    legacy_custom_nbt_items: int = 0
    unresolved_text: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        title = {
            "120-to-121": "FTB Quests 1.20.x → 1.21.x",
            "121-to-120": "FTB Quests 1.21.x → 1.20.x",
            "mixed": "Projeto SNBT misto",
            "unknown": "Projeto SNBT sem geração identificada",
        }.get(self.direction, self.direction)
        lines = [
            title,
            f"Capítulos: {self.chapters}",
            f"Quests: {self.quests}",
            f"Tasks: {self.tasks}",
            f"Rewards: {self.rewards}",
            f"Quest links: {self.quest_links}",
            f"Grupos: {self.groups}",
            f"Reward tables: {self.reward_tables}",
            f"Textos inline (estilo 1.20): {self.inline_strings}",
            f"Traduções externas (lang): {self.external_strings}",
        ]
        if self.conflicts:
            lines.append(f"Conflitos inline × lang: {self.conflicts}")
        if self.unresolved_text:
            lines.append(f"Textos sem ID seguro para migrar: {self.unresolved_text}")
        if self.legacy_custom_nbt_items:
            lines.append(f"ItemStacks com NBT legado/customizado: {self.legacy_custom_nbt_items}")
        if self.warnings:
            lines += ["", "Avisos:"] + [f"- {w}" for w in self.warnings]
        return "\n".join(lines)


@dataclass
class LegacyPortReport:
    direction: str
    source: Path
    destination: Path
    locale: str
    files_written: list[str] = field(default_factory=list)
    strings_migrated: int = 0
    conflicts: int = 0
    unresolved_text: int = 0
    legacy_custom_nbt_items: int = 0
    warnings: list[str] = field(default_factory=list)

    def add(self, path: Path | str) -> None:
        rel = str(path).replace("\\", "/")
        if rel not in self.files_written:
            self.files_written.append(rel)

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)

    def summary(self) -> str:
        lines = [
            self.direction,
            f"Strings migradas: {self.strings_migrated}",
            f"Arquivos gravados: {len(self.files_written)}",
        ]
        if self.conflicts:
            lines.append(f"Conflitos preservados a favor do lang existente: {self.conflicts}")
        if self.unresolved_text:
            lines.append(f"Textos mantidos inline por falta de ID: {self.unresolved_text}")
        if self.legacy_custom_nbt_items:
            lines.append(f"ItemStacks com NBT legado/customizado para revisar: {self.legacy_custom_nbt_items}")
        if self.warnings:
            lines += ["", "Avisos:"] + [f"- {w}" for w in self.warnings]
        return "\n".join(lines)


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    value = snbt_codec.load(path)
    return value if value is not None else copy.deepcopy(default)


def _read_lang(root: Path) -> dict[str, dict[str, Any]]:
    lang_root = root / "lang"
    out: dict[str, dict[str, Any]] = {}
    if not lang_root.exists():
        return out
    for p in sorted(lang_root.glob("*.snbt")):
        try:
            value = snbt_codec.load(p)
            if isinstance(value, dict):
                out.setdefault(p.stem, {}).update(value)
        except Exception:
            pass
    for loc_dir in sorted(p for p in lang_root.iterdir() if p.is_dir() and p.name != "recovery"):
        table = out.setdefault(loc_dir.name, {})
        for p in sorted(loc_dir.rglob("*.snbt")):
            if p.name.endswith(".snbt_merged"):
                continue
            try:
                value = snbt_codec.load(p)
                if isinstance(value, dict):
                    table.update(value)
            except Exception:
                pass
    return out


def _load_structure(root: Path):
    data = _load(root / "data.snbt", {})
    groups = _load(root / "chapter_groups.snbt", {"chapter_groups": []})
    chapters: list[tuple[Path, dict[str, Any]]] = []
    if (root / "chapters").exists():
        for p in sorted((root / "chapters").glob("*.snbt")):
            value = _load(p, {})
            if isinstance(value, dict):
                chapters.append((p, value))
    tables: list[tuple[Path, dict[str, Any]]] = []
    if (root / "reward_tables").exists():
        for p in sorted((root / "reward_tables").glob("*.snbt")):
            value = _load(p, {})
            if isinstance(value, dict):
                tables.append((p, value))
    if not isinstance(data, dict):
        data = {}
    if not isinstance(groups, dict):
        groups = {"chapter_groups": []}
    return data, groups, chapters, tables


def _value_present(value: Any) -> bool:
    return value not in (None, "", [])


def _put_translation(out: dict[str, Any], key: str, value: Any) -> None:
    if key and _value_present(value):
        out[key] = copy.deepcopy(value)


def _extract_inline(
    data: dict[str, Any],
    groups: dict[str, Any],
    chapters: list[tuple[Path, dict[str, Any]]],
    tables: list[tuple[Path, dict[str, Any]]],
    *,
    remove: bool,
) -> tuple[dict[str, Any], int]:
    """Collect 1.20-era inline text, optionally removing safely-keyed values."""
    out: dict[str, Any] = {}
    unresolved = 0

    def take(obj: dict[str, Any], field: str, key: str | None):
        nonlocal unresolved
        value = obj.get(field)
        if not _value_present(value):
            return
        if key:
            _put_translation(out, key, value)
            if remove:
                obj.pop(field, None)
        else:
            unresolved += 1

    take(data, "title", "file.0000000000000001.title")

    for g in groups.get("chapter_groups", []) or []:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("id", ""))
        take(g, "title", f"chapter_group.{gid}.title" if gid else None)

    for _, table in tables:
        tid = str(table.get("id", ""))
        take(table, "title", f"reward_table.{tid}.title" if tid else None)

    for _, ch in chapters:
        cid = str(ch.get("id", ""))
        take(ch, "title", f"chapter.{cid}.title" if cid else None)
        take(ch, "subtitle", f"chapter.{cid}.chapter_subtitle" if cid else None)

        for q in ch.get("quests", []) or []:
            if not isinstance(q, dict):
                continue
            qid = str(q.get("id", ""))
            take(q, "title", f"quest.{qid}.title" if qid else None)
            take(q, "subtitle", f"quest.{qid}.quest_subtitle" if qid else None)
            take(q, "description", f"quest.{qid}.quest_desc" if qid else None)
            for kind, bucket in (("task", "tasks"), ("reward", "rewards")):
                for obj in q.get(bucket, []) or []:
                    if not isinstance(obj, dict):
                        continue
                    oid = str(obj.get("id", ""))
                    take(obj, "title", f"{kind}.{oid}.title" if oid else None)

        for link in ch.get("quest_links", []) or []:
            if not isinstance(link, dict):
                continue
            lid = str(link.get("id", ""))
            take(link, "title", f"quest_link.{lid}.title" if lid else None)

    return out, unresolved


def _count_structure(groups, chapters, tables) -> dict[str, int]:
    counts = {"chapters": len(chapters), "quests": 0, "tasks": 0, "rewards": 0, "quest_links": 0,
              "groups": 0, "reward_tables": len(tables)}
    counts["groups"] = sum(1 for g in (groups.get("chapter_groups", []) or []) if isinstance(g, dict))
    for _, ch in chapters:
        quests = [q for q in (ch.get("quests", []) or []) if isinstance(q, dict)]
        counts["quests"] += len(quests)
        counts["quest_links"] += sum(1 for x in (ch.get("quest_links", []) or []) if isinstance(x, dict))
        for q in quests:
            counts["tasks"] += sum(1 for x in (q.get("tasks", []) or []) if isinstance(x, dict))
            counts["rewards"] += sum(1 for x in (q.get("rewards", []) or []) if isinstance(x, dict))
    return counts


def _count_legacy_custom_nbt(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        # 1.20 ItemStack-like payloads often use Count/tag.  Only count objects
        # that look like item stacks to avoid flagging arbitrary nested NBT.
        if "id" in value and ("tag" in value or "Count" in value or "Damage" in value):
            if "tag" in value and value.get("tag") not in (None, {}, ""):
                count += 1
        for v in value.values():
            count += _count_legacy_custom_nbt(v)
    elif isinstance(value, list):
        for v in value:
            count += _count_legacy_custom_nbt(v)
    return count


def analyze_legacy_snbt_port(source: Path | str, *, locale: str = "en_us") -> LegacyPortAnalysis:
    root = resolve_quest_root(source)
    if not root.exists():
        raise FileNotFoundError(root)
    if not (root / "chapters").exists() and not (root / "data.snbt").exists():
        raise ValueError("A origem não parece ser um Quest Book FTB Quests em SNBT.")

    data, groups, chapters, tables = _load_structure(root)
    inline, unresolved = _extract_inline(data, groups, chapters, tables, remove=False)
    langs = _read_lang(root)
    external = langs.get(locale, {})
    conflicts = sum(1 for k, v in inline.items() if k in external and _value_present(external[k]) and external[k] != v)

    if inline and external:
        direction = "mixed"
    elif inline:
        direction = "120-to-121"
    elif external:
        direction = "121-to-120"
    else:
        direction = "unknown"

    counts = _count_structure(groups, chapters, tables)
    custom_nbt = _count_legacy_custom_nbt(data) + _count_legacy_custom_nbt(groups)
    custom_nbt += sum(_count_legacy_custom_nbt(ch) for _, ch in chapters)
    custom_nbt += sum(_count_legacy_custom_nbt(t) for _, t in tables)
    analysis = LegacyPortAnalysis(
        source=root,
        direction=direction,
        locale=locale,
        inline_strings=len(inline),
        external_strings=len(external),
        conflicts=conflicts,
        unresolved_text=unresolved,
        legacy_custom_nbt_items=custom_nbt,
        **counts,
    )
    if direction == "mixed":
        analysis.warnings.append("Há texto inline e arquivo lang ao mesmo tempo. O projeto parece parcialmente migrado; revise os conflitos antes de portar.")
    if custom_nbt:
        analysis.warnings.append("Itens com custom NBT legado foram detectados. O Alpha preserva os dados, mas não tenta converter custom NBT arbitrário para componentes 1.21.")
    if unresolved:
        analysis.warnings.append("Alguns objetos têm texto mas não possuem ID seguro; esses textos serão mantidos inline para evitar perda.")
    return analysis


def _prepare_destination(src: Path, dst: Path, overwrite: bool) -> None:
    if src.resolve() == dst.resolve():
        raise ValueError("Origem e destino precisam ser diferentes.")
    if dst.exists() and any(dst.iterdir()):
        if not overwrite:
            raise FileExistsError(f"A pasta de destino não está vazia: {dst}")
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _save_structure(root: Path, data, groups, chapters, tables, report: LegacyPortReport) -> None:
    snbt_codec.save(root / "data.snbt", data); report.add("data.snbt")
    snbt_codec.save(root / "chapter_groups.snbt", groups); report.add("chapter_groups.snbt")
    for source_path, ch in chapters:
        target = root / "chapters" / source_path.name
        snbt_codec.save(target, ch); report.add(target.relative_to(root))
    for source_path, table in tables:
        target = root / "reward_tables" / source_path.name
        snbt_codec.save(target, table); report.add(target.relative_to(root))


def port_120_to_121(
    source: Path | str,
    destination: Path | str,
    *,
    locale: str = "en_us",
    overwrite: bool = False,
) -> LegacyPortReport:
    """Create a 1.21-style SNBT copy with translatable text externalized."""
    src = resolve_quest_root(source)
    dst = Path(destination)
    locale = (locale or "en_us").strip() or "en_us"
    _prepare_destination(src, dst, overwrite)

    data, groups, chapters, tables = _load_structure(dst)
    inline, unresolved = _extract_inline(data, groups, chapters, tables, remove=True)
    existing = _read_lang(dst).get(locale, {})
    merged = dict(inline)
    conflicts = 0
    # Existing translations are considered deliberate and therefore win over
    # text imported from legacy inline fields.
    for key, value in existing.items():
        if key in inline and _value_present(value) and inline[key] != value:
            conflicts += 1
        if _value_present(value) or key not in merged:
            merged[key] = copy.deepcopy(value)

    report = LegacyPortReport(
        "FTB Quests 1.20.x → 1.21.x",
        src,
        dst,
        locale,
        strings_migrated=len(inline),
        conflicts=conflicts,
        unresolved_text=unresolved,
    )
    custom_nbt = _count_legacy_custom_nbt(data) + _count_legacy_custom_nbt(groups)
    custom_nbt += sum(_count_legacy_custom_nbt(ch) for _, ch in chapters)
    custom_nbt += sum(_count_legacy_custom_nbt(t) for _, t in tables)
    report.legacy_custom_nbt_items = custom_nbt

    _save_structure(dst, data, groups, chapters, tables, report)
    lang_path = dst / "lang" / f"{locale}.snbt"
    snbt_codec.save(lang_path, merged); report.add(lang_path.relative_to(dst))

    if conflicts:
        report.warn("Já existiam traduções externas diferentes; elas foram preservadas e venceram o texto inline legado.")
    if unresolved:
        report.warn("Textos de objetos sem ID foram deixados inline para não perder conteúdo.")
    if custom_nbt:
        report.warn("Custom NBT de itens foi preservado, não convertido. Revise esses itens no Minecraft 1.21 após o port.")
    report.warn("A estrutura SNBT foi preservada. Abra a cópia no FTB Quests 1.21.x para permitir que o próprio mod conclua migrações estruturais/ItemStack específicas da versão.")
    return report


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _as_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return str(value)


def _inject_lang(data, groups, chapters, tables, table: dict[str, Any]) -> tuple[int, int]:
    applied = 0
    unresolved = 0

    def set_if(obj: dict[str, Any], field: str, key: str, transform=lambda x: x):
        nonlocal applied
        if key in table and _value_present(table[key]):
            obj[field] = transform(copy.deepcopy(table[key]))
            applied += 1

    # File title uses object id 1 in FTB Quests. Be tolerant of alternate
    # zero-padding by accepting the first file.*.title key as fallback.
    file_key = "file.0000000000000001.title"
    if file_key not in table:
        file_key = next((k for k in table if str(k).startswith("file.") and str(k).endswith(".title")), file_key)
    set_if(data, "title", file_key, _as_string)

    for g in groups.get("chapter_groups", []) or []:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("id", ""))
        if gid:
            set_if(g, "title", f"chapter_group.{gid}.title", _as_string)

    for _, rt in tables:
        rid = str(rt.get("id", ""))
        if rid:
            set_if(rt, "title", f"reward_table.{rid}.title", _as_string)

    for _, ch in chapters:
        cid = str(ch.get("id", ""))
        if cid:
            set_if(ch, "title", f"chapter.{cid}.title", _as_string)
            set_if(ch, "subtitle", f"chapter.{cid}.chapter_subtitle", _as_list)
        for q in ch.get("quests", []) or []:
            if not isinstance(q, dict):
                continue
            qid = str(q.get("id", ""))
            if qid:
                set_if(q, "title", f"quest.{qid}.title", _as_string)
                set_if(q, "subtitle", f"quest.{qid}.quest_subtitle", _as_string)
                set_if(q, "description", f"quest.{qid}.quest_desc", _as_list)
            for kind, bucket in (("task", "tasks"), ("reward", "rewards")):
                for obj in q.get(bucket, []) or []:
                    if not isinstance(obj, dict):
                        continue
                    oid = str(obj.get("id", ""))
                    if oid:
                        set_if(obj, "title", f"{kind}.{oid}.title", _as_string)
        for link in ch.get("quest_links", []) or []:
            if not isinstance(link, dict):
                continue
            lid = str(link.get("id", ""))
            if lid:
                set_if(link, "title", f"quest_link.{lid}.title", _as_string)

    return applied, unresolved


def port_121_to_120(
    source: Path | str,
    destination: Path | str,
    *,
    locale: str = "en_us",
    overwrite: bool = False,
    remove_lang: bool = True,
) -> LegacyPortReport:
    """Create a 1.20-style SNBT copy by embedding one locale in quest data."""
    src = resolve_quest_root(source)
    dst = Path(destination)
    locale = (locale or "en_us").strip() or "en_us"
    _prepare_destination(src, dst, overwrite)

    all_lang = _read_lang(dst)
    table = all_lang.get(locale)
    if not table:
        raise ValueError(f"Locale '{locale}' não encontrado ou vazio no Quest Book.")

    data, groups, chapters, tables = _load_structure(dst)
    applied, unresolved = _inject_lang(data, groups, chapters, tables, table)
    report = LegacyPortReport(
        "FTB Quests 1.21.x → 1.20.x",
        src,
        dst,
        locale,
        strings_migrated=applied,
        unresolved_text=unresolved,
    )
    _save_structure(dst, data, groups, chapters, tables, report)

    if remove_lang:
        lang_root = dst / "lang"
        if lang_root.exists():
            shutil.rmtree(lang_root)
            report.add("lang/ (removido no backport)")
    else:
        report.warn("A pasta lang foi mantida apenas como referência; FTB Quests 1.20.x não usa o sistema de traduções externas da linha 1.21.")

    other_locales = [x for x in all_lang if x != locale]
    if other_locales:
        report.warn("O formato 1.20.x embute um único texto no Quest Book. Apenas o locale selecionado foi injetado; outros idiomas não podem coexistir da mesma forma.")
    report.warn("O backport converte o sistema de texto. Propriedades exclusivas de versões mais novas podem não existir no FTB Quests 1.20.x e devem ser revisadas no jogo de destino.")
    return report
