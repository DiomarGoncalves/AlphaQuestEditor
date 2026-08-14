from __future__ import annotations

import re
import secrets
from pathlib import Path

from .lang import load_locale_tree, write_translation_value
from .models import ChapterGroupInfo, ChapterInfo, QuestInfo, RewardInfo, TaskInfo
from .json5_codec import load as load_json5, save as save_json5, dumps as dumps_json5, loads as loads_json5
from .format_conversion import detect_quest_format
from .snbt_scan import (
    extract_compound,
    extract_float,
    extract_list,
    extract_scalar,
    extract_string_list,
    find_key_value_start,
    find_matching,
    find_top_level_key_value_start,
    extract_top_level_scalar,
    split_top_level_compounds,
)


def _bool(text: str, key: str, default: bool = False) -> bool:
    raw = extract_scalar(text, key, "").lower()
    if raw in ("true", "1", "1b"):
        return True
    if raw in ("false", "0", "0b"):
        return False
    return default


def _int(text: str, key: str, default: int = 0, top_level: bool = False) -> int:
    raw = (extract_top_level_scalar(text, key, "") if top_level else extract_scalar(text, key, ""))
    raw = re.sub(r"[bBsSlLfFdD]$", "", raw)
    try:
        return int(float(raw))
    except Exception:
        return default


def _quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


class QuestBook:
    def __init__(self, modpack_root: Path):
        self.root = modpack_root
        self.quest_root = self._find_quest_root(modpack_root)
        detected = detect_quest_format(self.quest_root)
        self.storage_format = "json5" if detected in ("json5", "mixed") and (self.quest_root / "data.json5").exists() else ("json5" if detected == "json5" else "snbt")
        self.lang_pt_path = self.quest_root / "lang" / "pt_br.snbt"
        self.lang_en_path = self.quest_root / "lang" / "en_us.snbt"
        self.lang_pt: dict[str, str] = {}
        self.lang_en: dict[str, str] = {}
        self.chapters: list[ChapterInfo] = []
        self.chapter_groups: list[ChapterGroupInfo] = []
        self.group_by_id: dict[str, ChapterGroupInfo] = {}
        self.quest_by_id: dict[str, QuestInfo] = {}

    @staticmethod
    def _find_quest_root(root: Path) -> Path:
        candidates = [root / "config" / "ftbquests" / "quests", root / "ftbquests" / "quests", root]
        for c in candidates:
            if (c / "chapters").exists():
                return c
        return candidates[0]

    def load(self) -> None:
        detected = detect_quest_format(self.quest_root)
        if detected == "json5" or (detected == "mixed" and (self.quest_root / "data.json5").exists()):
            self.storage_format = "json5"
        elif detected == "snbt":
            self.storage_format = "snbt"
        self.lang_pt = load_locale_tree(self.quest_root, "pt_br", self.storage_format)
        self.lang_en = load_locale_tree(self.quest_root, "en_us", self.storage_format)
        self.chapters.clear(); self.chapter_groups.clear(); self.group_by_id.clear(); self.quest_by_id.clear()
        self._load_chapter_groups()
        chapters_dir = self.quest_root / "chapters"
        if not chapters_dir.exists():
            return
        pattern = "*.json5" if self.storage_format == "json5" else "*.snbt"
        for path in sorted(chapters_dir.glob(pattern)):
            chapter = self._load_chapter(path)
            self.chapters.append(chapter)
            for q in chapter.quests:
                self.quest_by_id.setdefault(q.quest_id, q)
        self._rebuild_dependents()

    def _rebuild_dependents(self) -> None:
        """Build reverse dependency links after every load.

        `QuestInfo.dependencies` answers "what must I finish before this quest?" while
        `QuestInfo.dependents` answers the opposite and is used by the visual
        relationship inspector. Keeping both directions avoids rescanning the whole
        book every time the user clicks a quest.
        """
        for q in self.quest_by_id.values():
            q.dependents.clear()
        for dependent in self.quest_by_id.values():
            for prerequisite_id in dependent.dependencies:
                prerequisite = self.quest_by_id.get(prerequisite_id)
                if prerequisite is not None and dependent.quest_id not in prerequisite.dependents:
                    prerequisite.dependents.append(dependent.quest_id)

    def _load_chapter_groups(self) -> None:
        if self.storage_format == "json5":
            path = self.quest_root / "chapter_groups.json5"
            if not path.exists(): return
            try: data = load_json5(path)
            except Exception: return
            for obj in (data.get("chapter_groups", []) if isinstance(data, dict) else []):
                if not isinstance(obj, dict): continue
                gid = str(obj.get("id", ""))
                if not gid: continue
                key = f"chapter_group.{gid}.title"
                icon = self._item_id(obj.get("icon"))
                g = ChapterGroupInfo(gid, key, self._title(key, str(obj.get("title") or "Grupo")), icon, dumps_json5(obj))
                self.chapter_groups.append(g); self.group_by_id[gid] = g
            return
        path = self.quest_root / "chapter_groups.snbt"
        if not path.exists():
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        raw = extract_list(text, "chapter_groups")
        for _, _, block in split_top_level_compounds(raw):
            gid = extract_scalar(block, "id", "")
            if not gid:
                continue
            key = f"chapter_group.{gid}.title"
            embedded = extract_scalar(block, "title", "")
            icon = extract_scalar(extract_compound(block, "icon"), "id", "")
            g = ChapterGroupInfo(gid, key, self._title(key, embedded or "Grupo"), icon, block)
            self.chapter_groups.append(g); self.group_by_id[gid] = g

    @staticmethod
    def _item_id(value) -> str:
        if isinstance(value, str): return value
        if isinstance(value, dict): return str(value.get("id", ""))
        return ""

    def _title(self, key: str, fallback: str = "") -> str:
        value = self.lang_pt.get(key) or self.lang_en.get(key)
        if value:
            return value
        kl = key.lower()
        for source in (self.lang_pt, self.lang_en):
            for k, v in source.items():
                if k.lower() == kl and v:
                    return v
        return fallback

    def _load_chapter(self, path: Path) -> ChapterInfo:
        if self.storage_format == "json5":
            try: data = load_json5(path)
            except Exception: data = {}
            if not isinstance(data, dict): data = {}
            cid = str(data.get("id", ""))
            title_key = f"chapter.{cid}.title" if cid else ""
            chapter = ChapterInfo(
                chapter_id=cid, title_key=title_key,
                title=self._title(title_key, str(data.get("title") or path.stem)),
                filename=str(data.get("filename") or path.stem), source_file=path,
                icon_item_id=self._item_id(data.get("icon")), group_id=str(data.get("group") or ""),
                order_index=int(data.get("order_index") or 0),
                default_quest_shape=str(data.get("default_quest_shape") or ""),
                default_quest_size=float(data.get("default_quest_size") or 1.0),
            )
            for obj in data.get("quests", []) or []:
                if isinstance(obj, dict): chapter.quests.append(self._parse_quest_json(obj, chapter, path))
            return chapter
        text = path.read_text(encoding="utf-8", errors="replace")
        cid = extract_top_level_scalar(text, "id", "")
        title_key = f"chapter.{cid}.title" if cid else ""
        icon = extract_scalar(extract_compound(text, "icon"), "id", "")
        embedded_title = extract_scalar(text, "title", "")
        chapter = ChapterInfo(
            chapter_id=cid, title_key=title_key, title=self._title(title_key, embedded_title or path.stem),
            filename=extract_top_level_scalar(text, "filename", path.stem), source_file=path, icon_item_id=icon,
            group_id=extract_top_level_scalar(text, "group", ""), order_index=_int(text, "order_index", 0, top_level=True),
            default_quest_shape=extract_scalar(text, "default_quest_shape", ""), default_quest_size=extract_float(text, "default_quest_size", 1.0),
        )
        list_start = find_key_value_start(text, "quests")
        if list_start < 0 or list_start >= len(text) or text[list_start] != "[": return chapter
        raw_list = extract_list(text, "quests"); base = list_start
        for rel_start, rel_end, block in split_top_level_compounds(raw_list):
            q = self._parse_quest(block, chapter, path); q.block_start = base + rel_start; q.block_end = base + rel_end; chapter.quests.append(q)
        return chapter

    def _parse_quest_json(self, obj: dict, chapter: ChapterInfo, path: Path) -> QuestInfo:
        qid = str(obj.get("id", "")); title_key=f"quest.{qid}.title" if qid else ""; desc_key=f"quest.{qid}.quest_desc" if qid else ""
        tasks=[]
        for task in obj.get("tasks", []) or []:
            if not isinstance(task, dict): continue
            tid=str(task.get("id", "")); ttype=str(task.get("type", "")); item_id=self._item_id(task.get("item")) or (str(task.get("item_id", "")) if ttype=="item" else "")
            task_icon=self._item_id(task.get("icon"))
            tasks.append(TaskInfo(task_id=tid, task_type=ttype, item_id=item_id, icon_item_id=task_icon, count=max(1,int(task.get("count") or 1)), title=self._title(f"task.{tid}.title" if tid else "", self._title(f"quest.{qid}.task.{tid}.title" if tid else "", "")), raw=dumps_json5(task)))
        rewards=[]
        for reward in obj.get("rewards", []) or []:
            if not isinstance(reward, dict): continue
            rid=str(reward.get("id", "")); rtype=str(reward.get("type", "item")); item_id=self._item_id(reward.get("item")); amount=reward.get("xp", reward.get("xp_levels", reward.get("value",0)))
            try: amount=int(amount or 0)
            except Exception: amount=0
            rewards.append(RewardInfo(reward_id=rid,reward_type=rtype,item_id=item_id,count=max(1,int(reward.get("count") or 1)),amount=amount,raw=dumps_json5(reward)))
        shape=str(obj.get("shape") or chapter.default_quest_shape or "")
        icon_obj=obj.get("icon")
        return QuestInfo(quest_id=qid,chapter_id=chapter.chapter_id,source_file=path,x=float(obj.get("x") or 0),y=float(obj.get("y") or 0),size=float(obj.get("size") or chapter.default_quest_size or 1),shape=shape,icon_item_id=self._item_id(icon_obj),icon_raw=(dumps_json5(icon_obj) if isinstance(icon_obj,dict) else str(icon_obj or "")),title_key=title_key,title=self._title(title_key,str(obj.get("title") or "")),description_key=desc_key,description=self._title(desc_key,""),dependencies=[str(x) for x in (obj.get("dependencies",[]) or [])],tasks=tasks,rewards=rewards,optional=bool(obj.get("optional",False)),invisible=bool(obj.get("invisible",False)),hide_until_deps_complete=str(obj.get("hide_until_deps_complete","default")),hide_until_deps_visible=str(obj.get("hide_until_deps_visible","default")),hide_dependency_lines=str(obj.get("hide_dependency_lines","default")),hide_dependent_lines=bool(obj.get("hide_dependent_lines",False)),require_sequential_tasks=str(obj.get("require_sequential_tasks","default")),can_repeat=str(obj.get("can_repeat","default")),min_required_dependencies=int(obj.get("min_required_dependencies") or 0),raw_block=dumps_json5(obj))

    def _parse_quest(self, block: str, chapter: ChapterInfo, path: Path) -> QuestInfo:
        qid = extract_scalar(block, "id", "")
        icon_compound = extract_compound(block, "icon")
        icon = extract_scalar(icon_compound, "id", "")
        title_key = f"quest.{qid}.title" if qid else ""; desc_key = f"quest.{qid}.quest_desc" if qid else ""
        tasks=[]
        for _,_,tb in split_top_level_compounds(extract_list(block,"tasks")):
            ttype=extract_scalar(tb,"type",""); tid=extract_scalar(tb,"id",""); item_comp=extract_compound(tb,"item"); item_id=extract_scalar(item_comp,"id","") if item_comp else ""
            if not item_id and ttype=="item": item_id=extract_scalar(tb,"item_id","")
            task_icon_comp=extract_compound(tb,"icon"); task_icon=extract_scalar(task_icon_comp,"id","") if task_icon_comp else ""
            tasks.append(TaskInfo(task_id=tid,task_type=ttype,item_id=item_id,icon_item_id=task_icon,count=max(1,_int(tb,"count",1,top_level=True)),title=self._title(f"task.{tid}.title" if tid else "", self._title(f"quest.{qid}.task.{tid}.title" if qid and tid else "", "")),raw=tb))
        rewards=[]
        for _,_,rb in split_top_level_compounds(extract_list(block,"rewards")):
            rtype=extract_scalar(rb,"type",""); rid=extract_scalar(rb,"id",""); item_comp=extract_compound(rb,"item"); item_id=extract_scalar(item_comp,"id","") if item_comp else ""
            rewards.append(RewardInfo(reward_id=rid,reward_type=rtype,item_id=item_id,count=max(1,_int(rb,"count",1,top_level=True)),amount=_int(rb,"xp",_int(rb,"xp_levels",_int(rb,"value",0))),raw=rb))
        embedded_title=extract_scalar(block,"title",""); shape=extract_scalar(block,"shape","") or chapter.default_quest_shape
        return QuestInfo(quest_id=qid,chapter_id=chapter.chapter_id,source_file=path,x=extract_float(block,"x",0.0),y=extract_float(block,"y",0.0),size=extract_float(block,"size",chapter.default_quest_size or 1.0),shape=shape,icon_item_id=icon,icon_raw=icon_compound,title_key=title_key,title=self._title(title_key,embedded_title),description_key=desc_key,description=self._title(desc_key,""),dependencies=extract_string_list(block,"dependencies"),tasks=tasks,rewards=rewards,optional=_bool(block,"optional",False),invisible=_bool(block,"invisible",False),hide_until_deps_complete=extract_scalar(block,"hide_until_deps_complete","default"),hide_until_deps_visible=extract_scalar(block,"hide_until_deps_visible","default"),hide_dependency_lines=extract_scalar(block,"hide_dependency_lines","default"),hide_dependent_lines=_bool(block,"hide_dependent_lines",False),require_sequential_tasks=extract_scalar(block,"require_sequential_tasks","default"),can_repeat=extract_scalar(block,"can_repeat","default"),min_required_dependencies=_int(block,"min_required_dependencies",0),raw_block=block)

    def display_title(self, quest: QuestInfo, item_name: str = "") -> str:
        return quest.title or item_name or "Quest sem título"

    def all_ids(self) -> set[str]:
        ids = set(self.quest_by_id)
        for g in self.chapter_groups:
            ids.add(g.group_id)
        for ch in self.chapters:
            ids.add(ch.chapter_id)
            for q in ch.quests:
                ids.update(t.task_id for t in q.tasks if t.task_id)
                ids.update(r.reward_id for r in q.rewards if r.reward_id)
        return ids

    def generate_id(self) -> str:
        used = self.all_ids()
        for _ in range(500):
            value = secrets.randbits(63) or 1
            out = f"{value:016X}".lstrip("0") or "1"
            if out not in used and int(out, 16) <= 0x7FFFFFFFFFFFFFFF:
                return out
        raise RuntimeError("Não foi possível gerar um ID único")

    def translation_owner_lookup(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for ch in self.chapters:
            stem = ch.filename or ch.source_file.stem
            for q in ch.quests:
                out[q.quest_id] = stem
                for t in q.tasks:
                    if t.task_id: out[t.task_id] = stem
                for r in q.rewards:
                    if r.reward_id: out[r.reward_id] = stem
            # Quest links/images are not modelled visually yet, but their translation
            # keys still need to land in the correct per-chapter language file.
            try:
                if self.storage_format == "json5":
                    raw = load_json5(ch.source_file)
                    for bucket in ("quest_links", "images"):
                        for obj in (raw.get(bucket, []) if isinstance(raw, dict) else []) or []:
                            if isinstance(obj, dict) and obj.get("id"): out[str(obj["id"])] = stem
            except Exception:
                pass
        return out

    def _write_translation(self, locale: str, key: str, value: str) -> None:
        write_translation_value(self.quest_root, locale, key, value, self.storage_format, self.translation_owner_lookup())

    def _json_chapter_data(self, chapter_or_quest) -> tuple[Path, dict]:
        path = chapter_or_quest.source_file
        data = load_json5(path) if path.exists() else {}
        return path, data if isinstance(data, dict) else {}

    def _json_find_quest(self, data: dict, quest_id: str):
        for q in data.get("quests", []) or []:
            if isinstance(q, dict) and str(q.get("id", "")) == quest_id:
                return q
        return None

    def save_title(self, quest: QuestInfo, title: str, also_english: bool = False) -> None:
        if not quest.title_key: return
        self._write_translation("pt_br", quest.title_key, title)
        if also_english: self._write_translation("en_us", quest.title_key, title)
        quest.title = title; self.lang_pt[quest.title_key] = title

    def save_description(self, quest: QuestInfo, description: str) -> None:
        if not quest.description_key: return
        self._write_translation("pt_br", quest.description_key, description)
        quest.description = description; self.lang_pt[quest.description_key] = description

    def save_translation_locale(self, locale: str, key: str, value: str) -> None:
        """Save one translation into the physical file that owns the key.

        This is used by the Crowdin-style importer: translators can hand the editor
        a consolidated/updated language file and Alpha routes each key back to the
        project's flat or split SNBT/JSON5 layout automatically.
        """
        locale = (locale or "pt_br").replace("-", "_").lower()
        self._write_translation(locale, key, value)
        if locale == "pt_br":
            self.lang_pt[key] = value
        elif locale == "en_us":
            self.lang_en[key] = value

    def save_translation(self, key: str, pt: str, en: str) -> None:
        self.save_translation_locale("pt_br", key, pt)
        self.save_translation_locale("en_us", key, en)

    def _find_quest_span(self, text: str, quest_id: str) -> tuple[int, int] | None:
        list_start = find_key_value_start(text, "quests")
        if list_start < 0: return None
        raw = extract_list(text, "quests")
        for rs, re_, block in split_top_level_compounds(raw):
            if extract_scalar(block, "id", "") == quest_id:
                return list_start + rs, list_start + re_
        return None

    def _replace_quest_block(self, quest: QuestInfo, transform) -> bool:
        text = quest.source_file.read_text(encoding="utf-8", errors="replace")
        span = self._find_quest_span(text, quest.quest_id)
        if not span: return False
        start, end = span; block = text[start:end]
        new_block = transform(block)
        if new_block is None: return False
        quest.source_file.write_text(text[:start] + new_block + text[end:], encoding="utf-8")
        return True

    @staticmethod
    def _set_scalar(block: str, key: str, rendered: str, *, remove_if: bool = False) -> str:
        # Only top-level key placement is intended; FTB quest blocks generally keep these properties top-level.
        pattern = re.compile(rf'(?m)^(\s*){re.escape(key)}\s*:\s*([^\n\r]+)')
        m = pattern.search(block)
        if remove_if:
            if m:
                start, end = m.span()
                while end < len(block) and block[end] in "\r\n": end += 1
                return block[:start] + block[end:]
            return block
        if m:
            return block[:m.start(2)] + rendered + block[m.end(2):]
        idm = re.search(r'(?m)^\s*id\s*:\s*(?:"[^"]*"|[^\s,}]+)[^\n\r]*', block)
        pos = idm.end() if idm else 1
        indent = "\n\t\t"
        return block[:pos] + f"{indent}{key}: {rendered}" + block[pos:]

    @staticmethod
    def _set_top_level_scalar(block: str, key: str, rendered: str, *, remove_if: bool = False) -> str:
        value_start = find_top_level_key_value_start(block, key)
        if value_start >= 0:
            # Locate the key line start and scalar end; chapter-level metadata is scalar.
            line_start = block.rfind("\n", 0, value_start) + 1
            value_end = value_start
            if value_start < len(block) and block[value_start] in ('"', "'"):
                quote = block[value_start]; value_end = value_start + 1
                while value_end < len(block):
                    if block[value_end] == "\\": value_end += 2; continue
                    if block[value_end] == quote: value_end += 1; break
                    value_end += 1
            else:
                while value_end < len(block) and block[value_end] not in "\n\r,}": value_end += 1
            if remove_if:
                end = block.find("\n", value_end)
                if end < 0: end = value_end
                else: end += 1
                return block[:line_start] + block[end:]
            return block[:value_start] + rendered + block[value_end:]
        if remove_if: return block
        close = block.rfind("}")
        pos = close if close >= 0 else len(block)
        return block[:pos] + f"\n\t{key}: {rendered}" + block[pos:]

    @staticmethod
    def _replace_list(block: str, key: str, rendered_list: str) -> str:
        value_start = find_key_value_start(block, key)
        if value_start >= 0 and value_start < len(block) and block[value_start] == "[":
            close = find_matching(block, value_start, "[", "]")
            if close >= 0:
                return block[:value_start] + rendered_list + block[close + 1:]
        idm = re.search(r'(?m)^\s*id\s*:\s*(?:"[^"]*"|[^\s,}]+)[^\n\r]*', block)
        pos = idm.end() if idm else 1
        return block[:pos] + f"\n\t\t{key}: {rendered_list}" + block[pos:]

    def save_position(self, quest: QuestInfo, x: float, y: float) -> bool:
        if self.storage_format == "json5":
            path, data = self._json_chapter_data(quest); obj = self._json_find_quest(data, quest.quest_id)
            if obj is None: return False
            obj["x"], obj["y"] = float(x), float(y); save_json5(path, data); quest.x, quest.y = float(x), float(y); return True
        def transform(block: str) -> str:
            def fmt(v): return f"{v:.3f}".rstrip("0").rstrip(".") + "d"
            return self._set_scalar(self._set_scalar(block, "x", fmt(x)), "y", fmt(y))
        ok = self._replace_quest_block(quest, transform)
        if ok: quest.x, quest.y = x, y
        return ok

    def save_positions(self, changes: list[tuple[QuestInfo, float, float]]) -> bool:
        """Persist a visual multi-move as one logical operation.

        Each replacement re-reads the latest file contents, so multiple quests in the
        same chapter stay safe even though earlier replacements change character offsets.
        The caller is responsible for creating a single backup for the whole transaction.
        """
        ok = True
        for quest, x, y in changes:
            ok = self.save_position(quest, float(x), float(y)) and ok
        return ok

    def save_properties(self, quest: QuestInfo, values: dict) -> bool:
        if self.storage_format == "json5":
            path, data = self._json_chapter_data(quest); obj = self._json_find_quest(data, quest.quest_id)
            if obj is None: return False
            size=float(values.get("size", quest.size or 1.0)); shape=str(values.get("shape","")).strip()
            if abs(size-1.0)<1e-9: obj.pop("size",None)
            else: obj["size"]=size
            if shape: obj["shape"]=shape
            else: obj.pop("shape",None)
            for key in ("optional", "invisible", "hide_dependent_lines"):
                val = bool(values.get(key, False))
                if val:
                    obj[key] = True
                else:
                    obj.pop(key, None)
            for key in ("hide_until_deps_complete","hide_until_deps_visible","hide_dependency_lines","require_sequential_tasks","can_repeat"):
                val=str(values.get(key,"default") or "default").lower()
                if val=="default": obj.pop(key,None)
                else: obj[key]=val
            mrd=int(values.get("min_required_dependencies",0) or 0)
            if mrd>0: obj["min_required_dependencies"]=mrd
            else: obj.pop("min_required_dependencies",None)
            save_json5(path,data); return True
        def tri(v: str) -> tuple[str, bool]:
            v = str(v or "default").lower()
            return (v, v == "default")
        def transform(block: str) -> str:
            out = block
            size = float(values.get("size", quest.size or 1.0))
            out = self._set_scalar(out, "size", f"{size:.3f}".rstrip("0").rstrip(".") + "d", remove_if=abs(size - 1.0) < 1e-9)
            shape = str(values.get("shape", "")).strip()
            out = self._set_scalar(out, "shape", _quote(shape), remove_if=not shape)
            for key in ("optional", "invisible", "hide_dependent_lines"):
                val = bool(values.get(key, False))
                out = self._set_scalar(out, key, "true" if val else "false", remove_if=not val)
            for key in ("hide_until_deps_complete", "hide_until_deps_visible", "hide_dependency_lines", "require_sequential_tasks", "can_repeat"):
                val, remove = tri(values.get(key, "default"))
                out = self._set_scalar(out, key, val, remove_if=remove)
            mrd = int(values.get("min_required_dependencies", 0) or 0)
            out = self._set_scalar(out, "min_required_dependencies", str(mrd), remove_if=mrd <= 0)
            return out
        return self._replace_quest_block(quest, transform)

    def set_dependencies(self, quest: QuestInfo, deps: list[str]) -> bool:
        deps = [d for d in dict.fromkeys(deps) if d and d != quest.quest_id]
        if self.storage_format == "json5":
            path,data=self._json_chapter_data(quest); obj=self._json_find_quest(data,quest.quest_id)
            if obj is None:return False
            if deps: obj["dependencies"]=deps
            else: obj.pop("dependencies",None)
            save_json5(path,data); quest.dependencies=list(deps); return True
        rendered = "[ " + " ".join(_quote(d) for d in deps) + " ]" if deps else "[ ]"
        return self._replace_quest_block(quest, lambda block: self._replace_list(block, "dependencies", rendered))

    def batch_update_dependencies(self, quests: list[QuestInfo], target_ids: list[str], mode: str = "add") -> tuple[bool, int]:
        """Add/remove the same dependency set on many quests as one logical edit.

        Existing dependencies are preserved in add mode. Self-dependencies are always
        ignored. The caller owns backup/history so the full batch can be undone at once.
        """
        targets = [d for d in dict.fromkeys(target_ids) if d and d in self.quest_by_id]
        mode = "remove" if str(mode).lower() == "remove" else "add"
        ok = True
        changed = 0
        seen = set()
        for quest in quests:
            if not quest or not quest.quest_id or quest.quest_id in seen:
                continue
            seen.add(quest.quest_id)
            current = list(dict.fromkeys(quest.dependencies))
            if mode == "add":
                new_deps = current + [d for d in targets if d != quest.quest_id and d not in current]
            else:
                remove = set(targets)
                new_deps = [d for d in current if d not in remove]
            new_deps = [d for d in dict.fromkeys(new_deps) if d and d != quest.quest_id]
            if new_deps == current:
                continue
            one_ok = self.set_dependencies(quest, new_deps)
            ok = one_ok and ok
            if one_ok:
                quest.dependencies = new_deps
                changed += 1
        return ok, changed

    def map_dependencies(self, prerequisite_ids: list[str], dependent_ids: list[str], mode: str = "add") -> tuple[bool, int]:
        """Apply an explicit prerequisite -> dependent relationship map.

        ``prerequisite_ids`` are written into the ``dependencies`` list of every
        quest listed in ``dependent_ids``. Add mode preserves existing
        dependencies; remove mode only removes the requested relationship.
        """
        prereqs = [qid for qid in dict.fromkeys(prerequisite_ids or []) if qid in self.quest_by_id]
        dependent_quests = [self.quest_by_id[qid] for qid in dict.fromkeys(dependent_ids or []) if qid in self.quest_by_id]
        return self.batch_update_dependencies(dependent_quests, prereqs, mode)

    def delete_quest(self, quest: QuestInfo) -> bool:
        if self.storage_format == "json5":
            path,data=self._json_chapter_data(quest); quests=data.get("quests",[]) or []; before=len(quests)
            data["quests"]=[q for q in quests if not (isinstance(q,dict) and str(q.get("id",""))==quest.quest_id)]
            if len(data["quests"])==before:return False
            save_json5(path,data)
            for other in list(self.quest_by_id.values()):
                if other.quest_id != quest.quest_id and quest.quest_id in other.dependencies:self.set_dependencies(other,[d for d in other.dependencies if d!=quest.quest_id])
            return True
        text = quest.source_file.read_text(encoding="utf-8", errors="replace")
        span = self._find_quest_span(text, quest.quest_id)
        if not span: return False
        start, end = span
        while start > 0 and text[start - 1] in " \t": start -= 1
        if start > 0 and text[start - 1] == "\n": start -= 1
        while end < len(text) and text[end] in " \t": end += 1
        if end < len(text) and text[end] == "\n": end += 1
        quest.source_file.write_text(text[:start] + text[end:], encoding="utf-8")
        # Match the in-game editor expectation: deleting a quest should not leave dangling dependency IDs.
        for other in list(self.quest_by_id.values()):
            if other.quest_id != quest.quest_id and quest.quest_id in other.dependencies:
                self.set_dependencies(other, [d for d in other.dependencies if d != quest.quest_id])
        return True

    def _insert_quest_block(self, chapter: ChapterInfo, block: str) -> bool:
        text = chapter.source_file.read_text(encoding="utf-8", errors="replace")
        list_start = find_key_value_start(text, "quests")
        if list_start < 0 or text[list_start] != "[": return False
        close = find_matching(text, list_start, "[", "]")
        if close < 0: return False
        inner = text[list_start + 1:close]
        prefix = "\n" if inner.strip() else "\n"
        insertion = prefix + "\t" + block.replace("\n", "\n\t") + "\n"
        chapter.source_file.write_text(text[:close] + insertion + text[close:], encoding="utf-8")
        return True

    def create_quest(self, chapter: ChapterInfo, title: str, x: float, y: float, item_id: str = "", task_type: str = "item", count: int = 1) -> str | None:
        qid, tid = self.generate_id(), self.generate_id()
        if self.storage_format == "json5":
            path,data=self._json_chapter_data(chapter); q={"x":float(x),"y":float(y),"id":qid}; count=max(1,int(count or 1))
            if task_type=="item" and item_id:q["tasks"]=[{"id":tid,"type":"item","item":{"id":item_id,"count":1},**({"count":count} if count>1 else {})}]
            elif task_type=="checkmark":q["tasks"]=[{"id":tid,"type":"checkmark"}]
            elif task_type=="xp":q["tasks"]=[{"id":tid,"type":"xp","value":count,"points":False}]
            data.setdefault("quests",[]).append(q); save_json5(path,data); self._write_translation("pt_br",f"quest.{qid}.title",title or "Nova Quest"); return qid
        count = max(1, int(count or 1))
        lines = ["{", f'\tid: "{qid}"', f"\tx: {x:.3f}d", f"\ty: {y:.3f}d"]
        if task_type == "item" and item_id:
            lines += ["\ttasks: [{", f'\t\tid: "{tid}"', '\t\ttype: "item"', f'\t\titem: {{count: 1 id: "{item_id}"}}']
            if count > 1: lines.append(f"\t\tcount: {count}L")
            lines += ["\t}]" ]
        elif task_type == "checkmark":
            lines += [f'\ttasks: [{{id: "{tid}" type: "checkmark"}}]']
        elif task_type == "xp":
            lines += [f'\ttasks: [{{id: "{tid}" type: "xp" value: {count}L points: false}}]']
        lines.append("}")
        if not self._insert_quest_block(chapter, "\n".join(lines)): return None
        self._write_translation("pt_br", f"quest.{qid}.title", title or "Nova Quest")
        return qid

    def duplicate_quest(self, quest: QuestInfo, dx: float = 1.0, dy: float = 1.0) -> str | None:
        if self.storage_format == "json5":
            import copy
            path,data=self._json_chapter_data(quest); original=self._json_find_quest(data,quest.quest_id)
            if original is None:return None
            clone=copy.deepcopy(original); new_qid=self.generate_id(); clone["id"]=new_qid; clone["x"]=float(quest.x+dx); clone["y"]=float(quest.y+dy)
            for bucket in ("tasks","rewards"):
                for child in clone.get(bucket,[]) or []:
                    if isinstance(child,dict) and child.get("id"):child["id"]=self.generate_id()
            data.setdefault("quests",[]).append(clone); save_json5(path,data)
            title=self.lang_pt.get(quest.title_key,quest.title or "Quest"); en=self.lang_en.get(quest.title_key,""); desc_pt=self.lang_pt.get(quest.description_key,quest.description or ""); desc_en=self.lang_en.get(quest.description_key,"")
            self._write_translation("pt_br",f"quest.{new_qid}.title",f"{title} (cópia)")
            if en:self._write_translation("en_us",f"quest.{new_qid}.title",f"{en} (copy)")
            if desc_pt:self._write_translation("pt_br",f"quest.{new_qid}.quest_desc",desc_pt)
            if desc_en:self._write_translation("en_us",f"quest.{new_qid}.quest_desc",desc_en)
            return new_qid
        text = quest.source_file.read_text(encoding="utf-8", errors="replace")
        span = self._find_quest_span(text, quest.quest_id)
        if not span: return None
        block = text[span[0]:span[1]]
        new_qid = self.generate_id()
        # Replace quest-level ID only (first top-level id line).
        block = re.sub(r'(\bid\s*:\s*)(?:"[^"]*"|[^\s,}]+)', lambda m: m.group(1) + _quote(new_qid), block, count=1)
        # Regenerate task/reward IDs without touching nested item IDs.
        for list_key in ("tasks", "rewards"):
            raw = extract_list(block, list_key)
            if not raw: continue
            updated = raw
            offset = 0
            for rs, re_, child in split_top_level_compounds(raw):
                old_id = extract_scalar(child, "id", "")
                if not old_id: continue
                new_id = self.generate_id()
                new_child = re.sub(r'(\bid\s*:\s*)(?:"[^"]*"|[^\s,}]+)', lambda m: m.group(1) + _quote(new_id), child, count=1)
                a, b = rs + offset, re_ + offset
                updated = updated[:a] + new_child + updated[b:]
                offset += len(new_child) - (re_ - rs)
            block = self._replace_list(block, list_key, updated)
        def fmt(v): return f"{v:.3f}".rstrip("0").rstrip(".") + "d"
        block = self._set_scalar(self._set_scalar(block, "x", fmt(quest.x + dx)), "y", fmt(quest.y + dy))
        chapter = next((c for c in self.chapters if c.chapter_id == quest.chapter_id), None)
        if not chapter or not self._insert_quest_block(chapter, block): return None
        title = self.lang_pt.get(quest.title_key, quest.title or "Quest")
        en = self.lang_en.get(quest.title_key, "")
        desc_pt = self.lang_pt.get(quest.description_key, quest.description or "")
        desc_en = self.lang_en.get(quest.description_key, "")
        self._write_translation("pt_br", f"quest.{new_qid}.title", f"{title} (cópia)")
        if en: self._write_translation("en_us", f"quest.{new_qid}.title", f"{en} (copy)")
        if desc_pt: self._write_translation("pt_br", f"quest.{new_qid}.quest_desc", desc_pt)
        if desc_en: self._write_translation("en_us", f"quest.{new_qid}.quest_desc", desc_en)
        return new_qid

    def _groups_file_text(self) -> tuple[Path, str]:
        path = self.quest_root / "chapter_groups.snbt"
        if path.exists():
            return path, path.read_text(encoding="utf-8", errors="replace")
        return path, "{\n\tchapter_groups: [ ]\n}\n"

    def _insert_group_block(self, block: str) -> bool:
        path, text = self._groups_file_text()
        value_start = find_key_value_start(text, "chapter_groups")
        if value_start < 0 or value_start >= len(text) or text[value_start] != "[":
            text = "{\n\tchapter_groups: [ ]\n}\n"; value_start = find_key_value_start(text, "chapter_groups")
        close = find_matching(text, value_start, "[", "]")
        if close < 0: return False
        insertion = "\n\t\t" + block.replace("\n", "\n\t\t") + "\n\t"
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text[:close] + insertion + text[close:], encoding="utf-8")
        return True

    def create_group(self, title: str) -> str | None:
        gid = self.generate_id()
        if self.storage_format == "json5":
            path=self.quest_root/"chapter_groups.json5"; data=load_json5(path) if path.exists() else {"chapter_groups":[]}
            if not isinstance(data,dict):data={"chapter_groups":[]}
            data.setdefault("chapter_groups",[]).append({"id":gid}); save_json5(path,data); self._write_translation("pt_br",f"chapter_group.{gid}.title",title.strip() or "Novo Grupo"); return gid
        if not self._insert_group_block(f'{{id: "{gid}"}}'): return None
        self._write_translation("pt_br", f"chapter_group.{gid}.title", title.strip() or "Novo Grupo")
        return gid

    def _find_group_span(self, text: str, group_id: str) -> tuple[int, int] | None:
        start = find_key_value_start(text, "chapter_groups")
        if start < 0: return None
        raw = extract_list(text, "chapter_groups")
        for rs, re_, block in split_top_level_compounds(raw):
            if extract_scalar(block, "id", "") == group_id: return start + rs, start + re_
        return None

    def edit_group(self, group: ChapterGroupInfo, title: str, new_id: str | None = None) -> bool:
        new_id = (new_id or group.group_id).strip()
        if self.storage_format == "json5":
            if not new_id or (new_id!=group.group_id and new_id in self.all_ids()):return False
            path=self.quest_root/"chapter_groups.json5"; data=load_json5(path) if path.exists() else {"chapter_groups":[]}
            found=False
            for obj in data.get("chapter_groups",[]) or []:
                if isinstance(obj,dict) and str(obj.get("id",""))==group.group_id:obj["id"]=new_id;found=True;break
            if not found:return False
            save_json5(path,data); self._write_translation("pt_br",f"chapter_group.{new_id}.title",title.strip() or group.title or "Grupo")
            if new_id!=group.group_id:
                for ch in self.chapters:
                    if ch.group_id==group.group_id:
                        cpath,cdata=self._json_chapter_data(ch); cdata["group"]=new_id; save_json5(cpath,cdata)
            return True
        if not new_id or (new_id != group.group_id and new_id in self.all_ids()): return False
        path, text = self._groups_file_text(); span = self._find_group_span(text, group.group_id)
        if not span: return False
        block = text[span[0]:span[1]]
        block = re.sub(r'(\bid\s*:\s*)(?:"[^"]*"|[^\s,}]+)', lambda m: m.group(1)+_quote(new_id), block, count=1)
        path.write_text(text[:span[0]] + block + text[span[1]:], encoding="utf-8")
        self._write_translation("pt_br", f"chapter_group.{new_id}.title", title.strip() or group.title or "Grupo")
        if new_id != group.group_id:
            for ch in self.chapters:
                if ch.group_id == group.group_id:
                    ctext = ch.source_file.read_text(encoding="utf-8", errors="replace")
                    ctext = self._set_top_level_scalar(ctext, "group", _quote(new_id))
                    ch.source_file.write_text(ctext, encoding="utf-8")
        return True

    def delete_group(self, group: ChapterGroupInfo) -> bool:
        if self.storage_format == "json5":
            path=self.quest_root/"chapter_groups.json5"; data=load_json5(path) if path.exists() else {"chapter_groups":[]}; arr=data.get("chapter_groups",[]) or []; before=len(arr); data["chapter_groups"]=[o for o in arr if not(isinstance(o,dict) and str(o.get("id",""))==group.group_id)]
            if len(data["chapter_groups"])==before:return False
            save_json5(path,data)
            for ch in self.chapters:
                if ch.group_id==group.group_id:
                    cpath,cdata=self._json_chapter_data(ch); cdata.pop("group",None); save_json5(cpath,cdata)
            return True
        path, text = self._groups_file_text(); span = self._find_group_span(text, group.group_id)
        if not span: return False
        a,b=span
        while a>0 and text[a-1] in " \t": a-=1
        if a>0 and text[a-1]=="\n": a-=1
        while b<len(text) and text[b] in " \t": b+=1
        if b<len(text) and text[b]=="\n": b+=1
        path.write_text(text[:a]+text[b:],encoding="utf-8")
        for ch in self.chapters:
            if ch.group_id == group.group_id:
                ctext=ch.source_file.read_text(encoding="utf-8",errors="replace")
                ctext=self._set_top_level_scalar(ctext,"group",_quote(""),remove_if=True)
                ch.source_file.write_text(ctext,encoding="utf-8")
        return True

    @staticmethod
    def _safe_filename(name: str) -> str:
        out = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_").lower()
        return out or "novo_capitulo"

    def create_chapter(self, title: str, filename: str = "", group_id: str = "", icon_item_id: str = "minecraft:book") -> str | None:
        cid=self.generate_id(); stem=self._safe_filename(filename or title)
        chapters_dir=self.quest_root/"chapters"; chapters_dir.mkdir(parents=True,exist_ok=True)
        suffix=".json5" if self.storage_format=="json5" else ".snbt"; path=chapters_dir/f"{stem}{suffix}"; n=2
        while path.exists(): path=chapters_dir/f"{stem}_{n}{suffix}"; n+=1
        siblings=[c.order_index for c in self.chapters if c.group_id==group_id]
        order=(max(siblings)+1) if siblings else 0
        if self.storage_format=="json5":
            data={"id":cid,"group":group_id,"order_index":order,"filename":path.stem,"quests":[],"quest_links":[],"images":[]}
            if icon_item_id:data["icon"]={"id":icon_item_id,"count":1}
            save_json5(path,data); self._write_translation("pt_br",f"chapter.{cid}.title",title.strip() or "Novo Capítulo"); return cid
        lines=["{", f'\tfilename: "{path.stem}"']
        if group_id: lines.append(f'\tgroup: "{group_id}"')
        if icon_item_id: lines += ["\ticon: {", f'\t\tid: "{icon_item_id}"', "\t}"]
        lines += [f'\tid: "{cid}"', f"\torder_index: {order}", "\tquests: [ ]", "}"]
        path.write_text("\n".join(lines)+"\n",encoding="utf-8")
        self._write_translation("pt_br", f"chapter.{cid}.title", title.strip() or "Novo Capítulo")
        return cid

    def edit_chapter(self, chapter: ChapterInfo, title: str, new_id: str | None = None, group_id: str | None = None, filename: str | None = None) -> bool:
        new_id=(new_id or chapter.chapter_id).strip(); group_id=chapter.group_id if group_id is None else group_id
        if not new_id or (new_id!=chapter.chapter_id and new_id in self.all_ids()): return False
        if self.storage_format=="json5":
            path,data=self._json_chapter_data(chapter); data["id"]=new_id
            if group_id:data["group"]=group_id
            else:data.pop("group",None)
            target=path
            if filename is not None:
                stem=self._safe_filename(filename); data["filename"]=stem; candidate=path.with_name(stem+".json5")
                if candidate!=path and candidate.exists():return False
                target=candidate
            save_json5(target,data)
            if target!=path:path.unlink()
            self._write_translation("pt_br",f"chapter.{new_id}.title",title.strip() or chapter.title or "Capítulo"); return True
        text=chapter.source_file.read_text(encoding="utf-8",errors="replace")
        text=self._set_top_level_scalar(text,"id",_quote(new_id))
        text=self._set_top_level_scalar(text,"group",_quote(group_id),remove_if=not group_id)
        target=chapter.source_file
        if filename is not None:
            stem=self._safe_filename(filename)
            text=self._set_top_level_scalar(text,"filename",_quote(stem))
            candidate=chapter.source_file.with_name(stem+".snbt")
            if candidate != chapter.source_file and candidate.exists(): return False
            target=candidate
        if new_id != chapter.chapter_id:
            # Dependencies use quest IDs, so only chapter metadata changes here.
            pass
        if target != chapter.source_file:
            target.write_text(text,encoding="utf-8"); chapter.source_file.unlink()
        else: target.write_text(text,encoding="utf-8")
        self._write_translation("pt_br", f"chapter.{new_id}.title", title.strip() or chapter.title or "Capítulo")
        return True

    def delete_chapter(self, chapter: ChapterInfo) -> bool:
        try:
            chapter.source_file.unlink(); return True
        except OSError:
            return False

    def replace_first_item_task(self, quest: QuestInfo, new_item_id: str) -> bool:
        if self.storage_format=="json5":
            path,data=self._json_chapter_data(quest); obj=self._json_find_quest(data,quest.quest_id)
            if obj is None:return False
            for task in obj.get("tasks",[]) or []:
                if isinstance(task,dict) and str(task.get("type",""))=="item":task["item"]={"id":new_item_id,"count":1};save_json5(path,data);return True
            return False
        def transform(block: str) -> str | None:
            task_match = re.search(r'type\s*:\s*"?item"?', block)
            if not task_match: return None
            item_pos = block.find("item", task_match.end())
            if item_pos < 0: return None
            brace = block.find("{", item_pos)
            if brace < 0: return None
            close = find_matching(block, brace, "{", "}")
            if close < 0: return None
            comp = block[brace:close + 1]
            id_re = re.compile(r'(\bid\s*:\s*)("[^"]*"|[A-Za-z0-9_./:+-]+)')
            m = id_re.search(comp)
            if not m: return None
            new_comp = comp[:m.start(2)] + _quote(new_item_id) + comp[m.end(2):]
            return block[:brace] + new_comp + block[close + 1:]
        return self._replace_quest_block(quest, transform)

    def set_tasks(self, quest: QuestInfo, task_specs: list[dict]) -> bool:
        if self.storage_format=="json5":
            path,data=self._json_chapter_data(quest); obj=self._json_find_quest(data,quest.quest_id)
            if obj is None:return False
            tasks=[]
            for spec in task_specs:
                ttype=str(spec.get("type","checkmark")); tid=str(spec.get("id") or self.generate_id()); spec["id"]=tid; raw=str(spec.get("raw") or "").strip()
                if raw and ttype not in ("item","checkmark","xp"):
                    try:
                        parsed=loads_json5(raw)
                        if isinstance(parsed,dict):parsed["id"]=tid;parsed.setdefault("type",ttype);tasks.append(parsed);continue
                    except Exception:pass
                child={"id":tid,"type":ttype}; icon_id=str(spec.get("icon_id","")).strip(); tags=[str(x).strip() for x in spec.get("tags",[]) if str(x).strip()]
                if icon_id:child["icon"]={"id":icon_id,"count":1}
                if tags:child["tags"]=tags
                if spec.get("optional_task"):child["optional_task"]=True
                if spec.get("disable_toast"):child["disable_toast"]=True
                if ttype=="item":
                    item=str(spec.get("item_id","")).strip(); count=max(1,int(spec.get("count",1) or 1)); child["item"]={"id":item,"count":1}
                    if count>1:child["count"]=count
                    consume=str(spec.get("consume_items","default"));crafting=str(spec.get("only_from_crafting","default"));match=str(spec.get("match_components","none"))
                    if consume in ("true","false"):child["consume_items"]=(consume=="true")
                    if crafting in ("true","false"):child["only_from_crafting"]=(crafting=="true")
                    if match and match!="none":child["match_components"]=match
                    if spec.get("task_screen_only"):child["task_screen_only"]=True
                elif ttype=="xp":
                    child["value"]=max(1,int(spec.get("count",spec.get("value",1)) or 1)); child["points"]=False
                tasks.append(child)
            obj["tasks"]=tasks if tasks else [] ; save_json5(path,data)
            for spec in task_specs:
                tid=str(spec.get("id") or "").strip(); title=str(spec.get("title") or "").strip()
                if tid and title:self._write_translation("pt_br",f"task.{tid}.title",title)
            return True
        rendered = []
        for spec in task_specs:
            ttype = str(spec.get("type", "checkmark"))
            tid = str(spec.get("id") or self.generate_id()); spec["id"] = tid
            raw = str(spec.get("raw") or "").strip()
            if raw and ttype not in ("item", "checkmark", "xp"):
                rendered.append(raw)
                continue
            extras = []
            icon_id = str(spec.get("icon_id", "")).strip()
            tags = [str(x).strip() for x in spec.get("tags", []) if str(x).strip()]
            if icon_id: extras.append(f'icon: {{id: "{icon_id}"}}')
            if tags: extras.append("tags: [" + " ".join(_quote(x) for x in tags) + "]")
            if spec.get("optional_task"): extras.append("optional_task: true")
            if spec.get("disable_toast"): extras.append("disable_toast: true")
            if ttype == "item":
                item = str(spec.get("item_id", "")).strip()
                count = max(1, int(spec.get("count", 1) or 1))
                child = f'{{id: "{tid}" type: "item" item: {{count: 1 id: "{item}"}}'
                if count > 1: child += f" count: {count}L"
                consume = str(spec.get("consume_items", "default"))
                crafting = str(spec.get("only_from_crafting", "default"))
                match = str(spec.get("match_components", "none"))
                if consume in ("true", "false"): extras.append(f"consume_items: {consume}")
                if crafting in ("true", "false"): extras.append(f"only_from_crafting: {crafting}")
                if match and match != "none": extras.append(f'match_components: "{match}"')
                if spec.get("task_screen_only"): extras.append("task_screen_only: true")
                if extras: child += " " + " ".join(extras)
                child += "}"
            elif ttype == "xp":
                value = max(1, int(spec.get("count", spec.get("value", 1)) or 1))
                child = f'{{id: "{tid}" type: "xp" value: {value}L points: false'
                if extras: child += " " + " ".join(extras)
                child += "}"
            else:
                child = f'{{id: "{tid}" type: "checkmark"'
                if extras: child += " " + " ".join(extras)
                child += "}"
            rendered.append(child)
        body = "[\n\t\t" + "\n\t\t".join(rendered) + "\n\t]" if rendered else "[ ]"
        ok = self._replace_quest_block(quest, lambda block: self._replace_list(block, "tasks", body))
        if ok:
            for spec in task_specs:
                tid = str(spec.get("id") or "").strip(); title = str(spec.get("title") or "").strip()
                if tid and title: self._write_translation("pt_br", f"task.{tid}.title", title)
        return ok

    def set_rewards(self, quest: QuestInfo, reward_specs: list[dict]) -> bool:
        if self.storage_format=="json5":
            path,data=self._json_chapter_data(quest); obj=self._json_find_quest(data,quest.quest_id)
            if obj is None:return False
            rewards=[]
            for spec in reward_specs:
                rtype=str(spec.get("type","item")); rid=str(spec.get("id") or self.generate_id()); spec["id"]=rid; raw=str(spec.get("raw") or "").strip()
                if raw and rtype not in ("item","xp","xp_levels"):
                    try:
                        parsed=loads_json5(raw)
                        if isinstance(parsed,dict):parsed["id"]=rid;parsed.setdefault("type",rtype);rewards.append(parsed);continue
                    except Exception:pass
                child={"id":rid,"type":rtype}
                if rtype=="item":
                    item=str(spec.get("item_id","")).strip();count=max(1,int(spec.get("count",1) or 1));child["item"]={"id":item,"count":1}
                    if count>1:child["count"]=count
                elif rtype=="xp_levels":child["xp_levels"]=max(1,int(spec.get("amount",spec.get("count",1)) or 1))
                else:child["xp"]=max(1,int(spec.get("amount",spec.get("count",1)) or 1))
                rewards.append(child)
            obj["rewards"]=rewards if rewards else []; save_json5(path,data); return True
        rendered = []
        for spec in reward_specs:
            rtype = str(spec.get("type", "item"))
            rid = str(spec.get("id") or self.generate_id())
            raw = str(spec.get("raw") or "").strip()
            if raw and rtype not in ("item", "xp", "xp_levels"):
                rendered.append(raw)
                continue
            if rtype == "item":
                item = str(spec.get("item_id", "")).strip()
                count = max(1, int(spec.get("count", 1) or 1))
                child = f'{{id: "{rid}" type: "item" item: {{count: 1 id: "{item}"}}'
                if count > 1: child += f" count: {count}"
                child += "}"
            elif rtype == "xp_levels":
                amount = max(1, int(spec.get("amount", spec.get("count", 1)) or 1))
                child = f'{{id: "{rid}" type: "xp_levels" xp_levels: {amount}}}'
            else:
                amount = max(1, int(spec.get("amount", spec.get("count", 1)) or 1))
                child = f'{{id: "{rid}" type: "xp" xp: {amount}L}}'
            rendered.append(child)
        body = "[\n\t\t" + "\n\t\t".join(rendered) + "\n\t]" if rendered else "[ ]"
        return self._replace_quest_block(quest, lambda block: self._replace_list(block, "rewards", body))
