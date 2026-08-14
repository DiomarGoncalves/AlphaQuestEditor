from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Iterable

from .models import AssetEntry, ItemEntry

DEFAULT_VANILLA_VERSION = "auto"
VANILLA_DATA_URLS = {
    "1.21.1": "https://raw.githubusercontent.com/PrismarineJS/minecraft-data/master/data/pc/1.21.1/items.json",
}
CACHE_VERSION = 5

_ID_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")


class ModIndex:
    """Version-tolerant offline asset/item index.

    The scanner does *not* execute Minecraft, NeoForge/Forge/Fabric or KubeJS.
    It extracts metadata and resources from JAR/ZIP files and KubeJS/resource-pack
    folders. This keeps it usable across Minecraft versions and allows the Asset
    Library to work without opening a quest book or a complete modpack.
    """

    def __init__(self) -> None:
        self.items: dict[str, ItemEntry] = {}
        self.images: dict[str, AssetEntry] = {}
        self.errors: list[str] = []
        self.quest_shapes: dict[str, bytes] = {}
        # ItemStack IDs used only as quest/task/chapter display icons. These can be
        # "virtual" from the editor's point of view (e.g. a Checkmark task icon)
        # even when they are not a gameplay item task.
        self.quest_display_items: set[str] = set()
        self.quest_custom_icon_data: dict[str, list[str]] = {}
        self.vanilla_catalog_status = ""
        self.loaded_from_cache = False
        self.minecraft_version = DEFAULT_VANILLA_VERSION
        self._root: Path | None = None
        self._sorted_items: list[ItemEntry] = []
        self._search_rows: list[tuple[str, ItemEntry]] = []
        self._sorted_images: list[AssetEntry] = []
        self._image_search_rows: list[tuple[str, AssetEntry]] = []
        self._display_exact: dict[str, str | None] = {}
        self._texture_cache: OrderedDict[str, bytes | None] = OrderedDict()
        self._asset_cache: OrderedDict[str, bytes | None] = OrderedDict()
        self._texture_cache_limit = 550
        self._asset_cache_limit = 260

    def clear(self) -> None:
        self.items.clear(); self.images.clear(); self.errors.clear(); self.quest_shapes.clear(); self.quest_display_items.clear(); self.quest_custom_icon_data.clear()
        self.vanilla_catalog_status = ""; self.loaded_from_cache = False
        self._sorted_items.clear(); self._search_rows.clear(); self._sorted_images.clear(); self._image_search_rows.clear()
        self._display_exact.clear(); self._texture_cache.clear(); self._asset_cache.clear()

    # ------------------------------------------------------------------
    # Version detection. Asset scanning itself is deliberately versionless.
    # ------------------------------------------------------------------
    @staticmethod
    def detect_minecraft_version(root: Path) -> str:
        candidates = [root / "manifest.json", root / "mmc-pack.json", root / "minecraftinstance.json", root / "profile.json"]
        for p in candidates:
            if not p.exists():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            if p.name == "manifest.json":
                v = ((data.get("minecraft") or {}).get("version") if isinstance(data, dict) else None)
                if v: return str(v)
            if p.name == "mmc-pack.json" and isinstance(data, dict):
                for c in data.get("components", []) or []:
                    if isinstance(c, dict) and c.get("uid") == "net.minecraft" and c.get("version"):
                        return str(c["version"])
            for key in ("minecraftVersion", "gameVersion", "version"):
                v = data.get(key) if isinstance(data, dict) else None
                if isinstance(v, str) and re.match(r"^(?:\d+\.\d+|\d{2}\.\d+)", v): return v
        cfg = root / "instance.cfg"
        if cfg.exists():
            text = cfg.read_text(encoding="utf-8", errors="ignore")
            for key in ("IntendedVersion", "MinecraftVersion", "mcVersion"):
                m = re.search(rf"(?mi)^\s*{re.escape(key)}\s*=\s*([^\r\n]+)", text)
                if m: return m.group(1).strip()
        return "auto"

    # ------------------------------------------------------------------
    # Persistent cache for complete modpack/project scans
    # ------------------------------------------------------------------
    def _cache_path(self, root: Path) -> Path:
        return root / ".alphaquest" / "cache" / "item_index_v5.json"

    @staticmethod
    def _stat_token(path: Path, base: Path | None = None) -> tuple[str, int, int]:
        st = path.stat()
        try: name = path.relative_to(base).as_posix() if base else str(path.resolve())
        except Exception: name = str(path.resolve())
        return name, int(st.st_size), int(st.st_mtime_ns)

    def _fingerprint(self, root: Path, vanilla_jar: Path | None = None) -> list[tuple[str, int, int]]:
        rows: list[tuple[str, int, int]] = []
        mods = root / "mods"
        if mods.exists():
            for p in sorted(mods.glob("*.jar")):
                try: rows.append(self._stat_token(p, root))
                except OSError: pass
        if vanilla_jar and vanilla_jar.exists():
            try: rows.append(self._stat_token(vanilla_jar))
            except OSError: pass
        for base in (root / "kubejs", root / "resourcepacks"):
            if not base.exists(): continue
            for p in sorted(base.rglob("*")):
                if p.is_file() and p.suffix.lower() in {".js", ".json", ".json5", ".png", ".lang"}:
                    try: rows.append(self._stat_token(p, root))
                    except OSError: pass
        return rows

    @staticmethod
    def _path_for_cache(path: Path | None, root: Path) -> str | None:
        if not path: return None
        try: return "rel:" + path.relative_to(root).as_posix()
        except Exception: return "abs:" + str(path)

    @staticmethod
    def _path_from_cache(value: str | None, root: Path) -> Path | None:
        if not value: return None
        if value.startswith("rel:"): return root / value[4:]
        if value.startswith("abs:"): return Path(value[4:])
        return Path(value)

    def _load_cache(self, root: Path, fingerprint) -> bool:
        p = self._cache_path(root)
        if not p.exists(): return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("version") != CACHE_VERSION or data.get("minecraft_version") != self.minecraft_version or data.get("fingerprint") != [list(x) for x in fingerprint]:
                return False
            for row in data.get("items", []):
                item_id = row.get("item_id", "")
                if ":" not in item_id: continue
                ns, rel = item_id.split(":", 1)
                self.items[item_id] = ItemEntry(item_id, ns, rel, row.get("display_name") or rel.replace("_", " ").title(), None,
                                                self._path_from_cache(row.get("source"), root), row.get("model_path"), row.get("texture_ref"))
            for row in data.get("images", []):
                aid = row.get("asset_id", "")
                if ":" not in aid: continue
                ns, rel = aid.split(":", 1)
                self.images[aid] = AssetEntry(aid, ns, rel, row.get("display_name") or rel, self._path_from_cache(row.get("source"), root), row.get("internal_path"), row.get("kind") or "image")
            self.quest_shapes = {k: base64.b64decode(v) for k, v in (data.get("quest_shapes") or {}).items() if isinstance(v, str)}
            self.vanilla_catalog_status = data.get("vanilla_catalog_status", "")
            self.loaded_from_cache = True; self._finalize_search_index(); return bool(self.items or self.images)
        except Exception as exc:
            self.errors.append(f"Cache de assets ignorado: {exc}"); return False

    def _save_cache(self, root: Path, fingerprint) -> None:
        try:
            p = self._cache_path(root); p.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": CACHE_VERSION, "minecraft_version": self.minecraft_version,
                "fingerprint": [list(x) for x in fingerprint], "vanilla_catalog_status": self.vanilla_catalog_status,
                "items": [{"item_id": e.item_id, "display_name": e.display_name, "source": self._path_for_cache(e.source_jar, root), "model_path": e.model_path, "texture_ref": e.texture_ref} for e in self._sorted_items],
                "images": [{"asset_id": e.asset_id, "display_name": e.display_name, "source": self._path_for_cache(e.source_file, root), "internal_path": e.internal_path, "kind": e.kind} for e in self._sorted_images],
                "quest_shapes": {k: base64.b64encode(v).decode("ascii") for k, v in self.quest_shapes.items()},
            }
            tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"); tmp.replace(p)
        except Exception as exc:
            self.errors.append(f"Não foi possível salvar cache do índice: {exc}")

    # ------------------------------------------------------------------
    # Public scans
    # ------------------------------------------------------------------
    def scan(self, modpack_root: Path, progress=None, force: bool = False, minecraft_version: str | None = None) -> None:
        self.clear(); self._root = Path(modpack_root)
        requested = str(minecraft_version or "auto")
        self.minecraft_version = self.detect_minecraft_version(self._root) if requested in {"", "auto", "None"} else requested
        if self.minecraft_version == "auto":
            cached = sorted((self._root / ".alphaquest" / "cache").glob("vanilla_items_*.json")) if (self._root / ".alphaquest" / "cache").exists() else []
            if len(cached) == 1:
                self.minecraft_version = cached[0].stem.removeprefix("vanilla_items_") or "auto"
        vanilla_jar = self._find_vanilla_client_jar(self._root) if self.minecraft_version != "auto" else None
        fingerprint = self._fingerprint(self._root, vanilla_jar)
        if not force and self._load_cache(self._root, fingerprint):
            if progress: progress(1, 1, "Cache de assets")
            return
        jars = sorted((self._root / "mods").glob("*.jar")) if (self._root / "mods").exists() else []
        if vanilla_jar and vanilla_jar not in jars: jars.insert(0, vanilla_jar)
        total = max(1, len(jars) + 3)
        for i, jar in enumerate(jars, 1):
            self._scan_archive(jar)
            if progress: progress(i, total, jar.name)
        self._scan_kubejs(self._root / "kubejs")
        self._scan_resourcepack_tree(self._root / "resourcepacks")
        if progress: progress(len(jars)+1, total, "KubeJS e resource packs")
        if self.minecraft_version != "auto": self._seed_vanilla_catalog(self._root)
        if progress: progress(len(jars)+2, total, f"Vanilla {self.minecraft_version}")
        self._finalize_search_index(); self._save_cache(self._root, fingerprint)
        if progress: progress(total, total, "Cache")

    def scan_sources(self, sources: Iterable[Path], kubejs_dir: Path | None = None, progress=None) -> None:
        """Scan arbitrary JAR/ZIP files/folders without opening a modpack.

        Folders are searched recursively for JARs. A KubeJS folder may be passed
        independently. This mode intentionally has no Minecraft-version requirement.
        """
        self.clear(); self.minecraft_version = "auto"; self._root = None
        archives: list[Path] = []
        resource_dirs: list[Path] = []
        for src in [Path(p) for p in sources]:
            if src.is_file() and src.suffix.lower() in {".jar", ".zip"}: archives.append(src)
            elif src.is_dir():
                found = sorted(src.rglob("*.jar")); archives.extend(found)
                # A direct assets tree/resource pack can also be indexed.
                if (src / "assets").exists() or (src / "pack.mcmeta").exists(): resource_dirs.append(src)
        # stable de-duplication
        archives = list(dict.fromkeys(p.resolve() for p in archives if p.exists()))
        total = max(1, len(archives) + len(resource_dirs) + (1 if kubejs_dir else 0))
        done = 0
        for jar in archives:
            self._scan_archive(jar); done += 1
            if progress: progress(done, total, jar.name)
        for d in resource_dirs:
            self._scan_resource_tree(d); done += 1
            if progress: progress(done, total, d.name)
        if kubejs_dir:
            self._scan_kubejs(Path(kubejs_dir)); done += 1
            if progress: progress(done, total, "KubeJS")
        self._finalize_search_index()

    # ------------------------------------------------------------------
    # Archive/resource extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _read_langs(zf: zipfile.ZipFile, names: set[str]) -> dict[str, str]:
        lang: dict[str, str] = {}
        # Prefer pt_br when present, then en_us, and support legacy .lang files.
        for locale in ("en_us", "pt_br"):
            for name in names:
                low = name.lower()
                if not low.startswith("assets/"): continue
                if low.endswith(f"/lang/{locale}.json"):
                    try:
                        data = json.loads(zf.read(name).decode("utf-8"))
                        if isinstance(data, dict):
                            for k, v in data.items():
                                if locale == "pt_br" or k not in lang: lang[str(k)] = str(v)
                    except Exception: pass
                elif low.endswith(f"/lang/{locale}.lang"):
                    try:
                        for line in zf.read(name).decode("utf-8", errors="ignore").splitlines():
                            if "=" not in line or line.lstrip().startswith("#"): continue
                            k, v = line.split("=", 1)
                            if locale == "pt_br" or k.strip() not in lang: lang[k.strip()] = v.strip()
                    except Exception: pass
        return lang

    def _scan_archive(self, archive: Path) -> None:
        try:
            with zipfile.ZipFile(archive) as zf:
                names = set(zf.namelist()); lang = self._read_langs(zf, names)
                # Every PNG becomes browsable. Item textures are also linked to entries below.
                for name in names:
                    if not (name.startswith("assets/") and name.lower().endswith(".png")): continue
                    parts = name.split("/")
                    if len(parts) < 4: continue
                    ns = parts[1]; rel = "/".join(parts[2:])[:-4]
                    aid = f"{ns}:{rel}"
                    self._ensure_image(aid, archive, name)
                    if "/textures/shapes/" in name and name.endswith("/shape.png"):
                        try:
                            shape_id = name.split("/textures/shapes/", 1)[1].rsplit("/shape.png", 1)[0]
                            if shape_id: self.quest_shapes.setdefault(shape_id, zf.read(name))
                        except Exception: pass
                # Legacy/current item model conventions.
                for name in names:
                    if not name.startswith("assets/") or not name.endswith(".json"): continue
                    parts = name.split("/")
                    if len(parts) < 4: continue
                    ns = parts[1]
                    rel = None
                    if "/models/item/" in name: rel = name.split("/models/item/", 1)[1][:-5]
                    elif "/items/" in name: rel = name.split("/items/", 1)[1][:-5]  # modern client item definitions
                    if rel is None: continue
                    display = self._display_for(lang, ns, rel)
                    texref = self._texture_from_item_definition(zf, names, ns, name)
                    self._ensure_entry(f"{ns}:{rel}", display, archive, texref, name)
                # Direct texture conventions (textures/item and older textures/items).
                for name in names:
                    if not (name.startswith("assets/") and name.lower().endswith(".png")): continue
                    marker = "/textures/item/" if "/textures/item/" in name else ("/textures/items/" if "/textures/items/" in name else None)
                    if not marker: continue
                    ns = name.split("/")[1]; rel = name.split(marker, 1)[1][:-4]
                    self._ensure_entry(f"{ns}:{rel}", self._display_for(lang, ns, rel), archive, f"{ns}:{marker.split('/textures/',1)[1].strip('/')}/{rel}")
                # Translation keys and data files recover code-registered items with no model.
                for key, display in lang.items():
                    m = re.match(r"^(?:item|block)\.([a-z0-9_.-]+)\.(.+)$", key)
                    if m:
                        ns, rel = m.group(1), m.group(2).replace(".", "/")
                        self._ensure_entry(f"{ns}:{rel}", str(display), archive)
                for item_id in self._candidate_ids_from_archive(zf, names): self._ensure_entry(item_id, source=archive)
        except Exception as exc:
            self.errors.append(f"{archive.name}: {exc}")

    @staticmethod
    def _display_for(lang: dict[str, str], ns: str, rel: str) -> str:
        dot = rel.replace("/", ".")
        return lang.get(f"item.{ns}.{dot}", "") or lang.get(f"block.{ns}.{dot}", "")

    def _candidate_ids_from_archive(self, zf: zipfile.ZipFile, names: set[str]) -> set[str]:
        ids: set[str] = set()
        for name in names:
            low = name.lower()
            if not (name.startswith("data/") and name.endswith(".json") and ("/tags/item" in low or "/recipes/" in low or "/recipe/" in low)):
                continue
            try: data = json.loads(zf.read(name).decode("utf-8"))
            except Exception: continue
            def walk(x):
                if isinstance(x, dict):
                    for k, v in x.items():
                        if k in {"item", "id"} and isinstance(v, str) and _ID_RE.match(v) and not v.startswith("#"): ids.add(v)
                        else: walk(v)
                elif isinstance(x, list):
                    for v in x: walk(v)
            walk(data)
        return ids

    def _texture_from_item_definition(self, zf: zipfile.ZipFile, names: set[str], ns: str, path: str) -> str | None:
        visited: set[str] = set()
        def load(p: str):
            try:
                d = json.loads(zf.read(p).decode("utf-8")); return d if isinstance(d, dict) else {}
            except Exception: return {}
        def find_ref(x):
            if isinstance(x, dict):
                # 1.21.4+ client item definition often points to a model resource here.
                for k in ("model", "texture"):
                    v = x.get(k)
                    if isinstance(v, str) and (":" in v or "/" in v):
                        yield v
                for v in x.values(): yield from find_ref(v)
            elif isinstance(x, list):
                for v in x: yield from find_ref(v)
        def resolve_model(model_path: str, depth=0):
            if depth > 10 or model_path in visited or model_path not in names: return None
            visited.add(model_path); data = load(model_path)
            tex = data.get("textures") if isinstance(data.get("textures"), dict) else {}
            for key in ("layer0", "particle", "all", "side", "front", "top"):
                ref = tex.get(key)
                if isinstance(ref, str) and not ref.startswith("#"):
                    tns, tpath = ref.split(":",1) if ":" in ref else (ns, ref)
                    if f"assets/{tns}/textures/{tpath}.png" in names: return f"{tns}:{tpath}"
            parent = data.get("parent")
            if isinstance(parent, str) and parent not in {"item/generated", "item/handheld", "builtin/entity"}:
                pns, ppath = parent.split(":",1) if ":" in parent else (ns, parent)
                got = resolve_model(f"assets/{pns}/models/{ppath}.json", depth+1)
                if got: return got
            return None
        data = load(path)
        # Existing model file.
        if "/models/item/" in path:
            return resolve_model(path)
        # Modern items/foo.json -> referenced model resource.
        for ref in find_ref(data):
            rns, rpath = ref.split(":",1) if ":" in ref else (ns, ref)
            model = f"assets/{rns}/models/{rpath}.json"
            got = resolve_model(model)
            if got: return got
            # It can also directly name a texture-like resource.
            if f"assets/{rns}/textures/{rpath}.png" in names: return f"{rns}:{rpath}"
        return None

    # ------------------------------------------------------------------
    # KubeJS support: modern + legacy script syntax and arbitrary assets.
    # ------------------------------------------------------------------
    def _scan_kubejs(self, kube: Path) -> None:
        if not kube or not kube.exists(): return
        self._scan_resource_tree(kube)
        for p in kube.rglob("*.js"):
            try: text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception: continue
            self._scan_kubejs_script(text, p)

    def _scan_kubejs_script(self, text: str, source: Path) -> None:
        # Matches event.create('foo') in StartupEvents.registry('item',...) and old item.registry handlers.
        # Unqualified names default to the KubeJS namespace, matching KubeJS behaviour.
        item_context = bool(re.search(r"registry\s*\(\s*['\"]item['\"]|item\.registry|registry\.item", text, re.I))
        block_context = bool(re.search(r"registry\s*\(\s*['\"]block['\"]|block\.registry|registry\.block", text, re.I))
        create_re = re.compile(r"\b(?:event\.)?create\s*\(\s*['\"]([a-z0-9_.:/-]+)['\"]", re.I)
        for m in create_re.finditer(text):
            raw = m.group(1).lower(); item_id = raw if ":" in raw else f"kubejs:{raw}"
            # In mixed files, only accept generic create() when an item/block registry is evident.
            if not (item_context or block_context): continue
            tail = text[m.end():m.end()+900]
            if block_context and ".noItem(" in tail: continue
            display = ""
            dm = re.search(r"\.displayName\s*\(\s*['\"]([^'\"]+)['\"]", tail, re.I)
            if dm: display = dm.group(1)
            texref = None
            tm = re.search(r"\.(?:texture|textureAll)\s*\(\s*(?:['\"][^'\"]+['\"]\s*,\s*)?['\"]([a-z0-9_.-]+:[a-z0-9_./-]+)['\"]", tail, re.I)
            if tm: texref = tm.group(1)
            self._ensure_entry(item_id, display, source, texref)
        # Explicit Item.of()/ItemStack references are useful for KubeJS-created virtual entries
        # and for packs whose resource assets exist without a conventional model.
        for m in re.finditer(r"\b(?:Item\.of|ItemStack\.of)\s*\(\s*['\"]([a-z0-9_.-]+:[a-z0-9_./-]+)['\"]", text, re.I):
            self._ensure_entry(m.group(1).lower(), source=source)

    def _scan_resourcepack_tree(self, root: Path) -> None:
        if not root.exists(): return
        for child in root.iterdir():
            if child.is_dir(): self._scan_resource_tree(child)
            elif child.suffix.lower() in {".zip", ".jar"}: self._scan_archive(child)

    def _scan_resource_tree(self, root: Path) -> None:
        # Accept both <root>/assets/... and KubeJS root containing assets/.
        assets = root / "assets" if (root / "assets").exists() else (root if root.name == "assets" else None)
        if not assets or not assets.exists(): return
        langs: dict[tuple[str,str], str] = {}
        for p in assets.rglob("lang/*.json"):
            try:
                ns = p.parent.parent.name; data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for k,v in data.items(): langs[(ns,str(k))]=str(v)
            except Exception: pass
        for p in assets.rglob("*.png"):
            try:
                rel = p.relative_to(assets); ns = rel.parts[0]; inside = Path(*rel.parts[1:]).with_suffix("").as_posix()
            except Exception: continue
            aid = f"{ns}:{inside}"; self._ensure_image(aid, p, None)
            m = re.match(r"textures/items?/(.+)$", inside)
            if m:
                item_rel = m.group(1); display = langs.get((ns,f"item.{ns}.{item_rel.replace('/','.')}"), "")
                self._ensure_entry(f"{ns}:{item_rel}", display, p, "file")
        for p in list(assets.rglob("models/item/*.json")) + list(assets.rglob("items/*.json")):
            try:
                rel = p.relative_to(assets); ns = rel.parts[0]
                marker = "models/item/" if "/models/item/" in rel.as_posix() else "items/"
                item_rel = rel.as_posix().split(marker,1)[1][:-5]
                display = langs.get((ns,f"item.{ns}.{item_rel.replace('/','.')}"), "")
                self._ensure_entry(f"{ns}:{item_rel}", display, p)
            except Exception: pass

    # ------------------------------------------------------------------
    # Quest-book display ItemStacks (including checkmark/custom task icons)
    # ------------------------------------------------------------------
    def register_questbook_icons(self, book) -> int:
        """Expose every ItemStack used visually by the quest book in the item index.

        FTB Quests may derive a quest icon from a task icon. A checkmark can therefore
        carry a decorative ItemStack/resource even though it is not an Item Task.
        Registering these references means the editor can search/show them and can use
        matching textures already discovered in JARs/KubeJS/resource packs.
        """
        old_display = set(self.quest_display_items)
        self.quest_display_items.clear(); self.quest_custom_icon_data.clear()
        # Remove only synthetic entries created from quest source files. Real JAR/KubeJS
        # entries remain in the shared index.
        for iid in old_display:
            e = self.items.get(iid)
            if e and e.source_jar and e.source_jar.suffix.lower() in {".snbt", ".json5"}:
                self.items.pop(iid, None)
        refs: list[tuple[str, str, Path | None, str]] = []
        for group in getattr(book, "chapter_groups", []) or []:
            if getattr(group, "icon_item_id", ""):
                refs.append((group.icon_item_id, f"Ícone de grupo — {group.title}", None, ""))
        for chapter in getattr(book, "chapters", []) or []:
            if getattr(chapter, "icon_item_id", ""):
                refs.append((chapter.icon_item_id, f"Ícone de capítulo — {chapter.title}", chapter.source_file, ""))
            for quest in chapter.quests:
                if quest.icon_item_id:
                    refs.append((quest.icon_item_id, f"Ícone de quest — {quest.title or quest.quest_id}", quest.source_file, quest.icon_raw or ""))
                for task in quest.tasks:
                    if task.icon_item_id:
                        kind = "Checkmark" if task.task_type == "checkmark" else (task.task_type or "Task")
                        refs.append((task.icon_item_id, f"Ícone {kind} — {quest.title or quest.quest_id}", quest.source_file, task.raw or ""))

        for item_id, label, source, raw in refs:
            if not item_id or ":" not in item_id:
                continue
            self.quest_display_items.add(item_id)
            if raw and any(x in raw.lower() for x in ("custom_model_data", "custom-model-data", "minecraft:item_model", "components", "custommodeldata")):
                bucket = self.quest_custom_icon_data.setdefault(item_id, [])
                if raw not in bucket: bucket.append(raw)
            if item_id not in self.items:
                ns, rel = item_id.split(":", 1)
                # If the pack contains only a texture (common for KubeJS/resource packs),
                # connect it to the synthetic item so it can still be previewed.
                img = self.images.get(f"{ns}:textures/item/{rel}") or self.images.get(f"{ns}:textures/items/{rel}")
                if img and img.source_file:
                    if img.source_file.suffix.lower() in {".jar", ".zip"}:
                        texref = f"{ns}:item/{rel}" if f"{ns}:textures/item/{rel}" in self.images else f"{ns}:items/{rel}"
                        self._ensure_entry(item_id, label, img.source_file, texref)
                    else:
                        self._ensure_entry(item_id, label, img.source_file)
                else:
                    self._ensure_entry(item_id, label, source)
            else:
                existing = self.items[item_id]
                # Keep a real mod translation when available; otherwise make the role clear.
                fallback = existing.path.replace("/", " ").replace("_", " ").title()
                if not existing.display_name or existing.display_name == fallback:
                    existing.display_name = label
        self._finalize_search_index()
        return len(self.quest_display_items)

    # ------------------------------------------------------------------
    # Entry helpers
    # ------------------------------------------------------------------
    def _ensure_entry(self, item_id: str, display: str = "", source: Path | None = None, texture_ref: str | None = None, model_path: str | None = None) -> None:
        if ":" not in item_id or item_id.startswith("#") or not _ID_RE.match(item_id): return
        ns, rel = item_id.split(":",1); existing = self.items.get(item_id)
        if existing:
            if texture_ref and not existing.texture_ref: existing.texture_ref = texture_ref
            if source and not existing.source_jar: existing.source_jar = Path(source)
            if model_path and not existing.model_path: existing.model_path = model_path
            if display and (not existing.display_name or existing.display_name == existing.path.replace("_", " ").title()): existing.display_name = display
            return
        self.items[item_id] = ItemEntry(item_id, ns, rel, display or rel.replace("/"," ").replace("_"," ").title(), None, Path(source) if source else None, model_path, texture_ref)

    def _ensure_image(self, asset_id: str, source: Path, internal_path: str | None) -> None:
        if ":" not in asset_id: return
        ns, rel = asset_id.split(":",1)
        if asset_id not in self.images:
            self.images[asset_id] = AssetEntry(asset_id, ns, rel, Path(rel).name.replace("_"," ").title(), Path(source), internal_path, "image")

    def _finalize_search_index(self) -> None:
        self._sorted_items = sorted(self.items.values(), key=lambda x:(x.namespace!="minecraft",x.namespace,x.display_name.casefold(),x.item_id))
        self._search_rows = [(f"{e.display_name} {e.item_id}".casefold(),e) for e in self._sorted_items]
        self._sorted_images = sorted(self.images.values(), key=lambda x:(x.namespace,x.path.casefold(),x.asset_id))
        self._image_search_rows = [(f"{e.display_name} {e.asset_id} {e.path}".casefold(),e) for e in self._sorted_images]
        self._display_exact.clear()
        for e in self._sorted_items:
            k=e.display_name.strip().casefold()
            if not k: continue
            if k not in self._display_exact:self._display_exact[k]=e.item_id
            elif self._display_exact[k]!=e.item_id:self._display_exact[k]=None

    def search(self, text: str, limit: int = 1000) -> list[ItemEntry]:
        q=(text or "").strip().casefold(); limit=max(1,int(limit)); tokens=[t for t in q.split() if t]
        if not tokens:return self._sorted_items[:limit]
        out=[]
        for hay,e in self._search_rows:
            if all(t in hay for t in tokens):
                out.append(e)
                if len(out)>=limit:break
        return out

    def search_images(self, text: str, limit: int = 1000) -> list[AssetEntry]:
        q=(text or "").strip().casefold(); limit=max(1,int(limit)); tokens=[t for t in q.split() if t]
        if not tokens:return self._sorted_images[:limit]
        out=[]
        for hay,e in self._image_search_rows:
            if all(t in hay for t in tokens):
                out.append(e)
                if len(out)>=limit:break
        return out

    def resolve_text(self,text:str)->str:
        text=(text or "").strip()
        if text in self.items:return text
        return self._display_exact.get(text.casefold()) or ""

    def get_texture_bytes(self,item_id:str)->bytes|None:
        if not item_id:return None
        if item_id in self._texture_cache:
            raw=self._texture_cache.pop(item_id);self._texture_cache[item_id]=raw;return raw
        e=self.items.get(item_id);raw=None
        if e and e.source_jar and e.source_jar.exists():
            try:
                src=e.source_jar
                if src.suffix.lower() in {".jar",".zip"} and e.texture_ref and ":" in e.texture_ref:
                    ns,rel=e.texture_ref.split(":",1)
                    # Support both item and items texture folder refs.
                    internal=f"assets/{ns}/textures/{rel}.png"
                    with zipfile.ZipFile(src) as zf:
                        raw=zf.read(internal) if internal in zf.namelist() else None
                elif src.suffix.lower()==".png":raw=src.read_bytes()
                elif src.suffix.lower()==".js" and e.texture_ref and ":" in e.texture_ref:
                    # KubeJS script entry: resolve texture in the nearest kubejs/assets tree.
                    cur=src.parent
                    for parent in [cur,*cur.parents]:
                        assets=parent/"assets"
                        if assets.exists():
                            ns,rel=e.texture_ref.split(":",1); p=assets/ns/"textures"/(rel+".png")
                            if p.exists(): raw=p.read_bytes();break
            except Exception:raw=None
        self._texture_cache[item_id]=raw
        if len(self._texture_cache)>self._texture_cache_limit:self._texture_cache.popitem(last=False)
        return raw

    def get_asset_bytes(self,asset_id:str)->bytes|None:
        if asset_id in self._asset_cache:
            raw=self._asset_cache.pop(asset_id);self._asset_cache[asset_id]=raw;return raw
        e=self.images.get(asset_id);raw=None
        if e and e.source_file and e.source_file.exists():
            try:
                if e.source_file.suffix.lower() in {".jar",".zip"} and e.internal_path:
                    with zipfile.ZipFile(e.source_file) as zf: raw=zf.read(e.internal_path)
                elif e.source_file.suffix.lower()==".png": raw=e.source_file.read_bytes()
            except Exception:raw=None
        self._asset_cache[asset_id]=raw
        if len(self._asset_cache)>self._asset_cache_limit:self._asset_cache.popitem(last=False)
        return raw

    # ------------------------------------------------------------------
    # Vanilla lookup (optional; exact local JAR is preferred for universality)
    # ------------------------------------------------------------------
    def _find_vanilla_client_jar(self, root: Path) -> Path | None:
        version=self.minecraft_version
        if not version or version=="auto":return None
        bases=[root,*list(root.parents)[:4]];home=Path.home();appdata=os.environ.get("APPDATA")
        if appdata:bases += [Path(appdata)/".minecraft",Path(appdata)/"PrismLauncher",Path(appdata)/"MultiMC"]
        bases += [home/".minecraft",home/"AppData"/"Roaming"/".minecraft",home/"AppData"/"Roaming"/"PrismLauncher"]
        candidates=[]
        for base in bases:
            candidates += [base/"versions"/version/f"{version}.jar",base/".minecraft"/"versions"/version/f"{version}.jar"]
        for p in candidates:
            if p.exists() and p.is_file():self.vanilla_catalog_status=f"Minecraft local: {p.name}";return p
        return None

    def _seed_vanilla_catalog(self, root: Path) -> None:
        version=self.minecraft_version;url=VANILLA_DATA_URLS.get(version)
        if not url:return
        cache=root/".alphaquest"/"cache"/f"vanilla_items_{version}.json";data=None
        if cache.exists():
            try:data=json.loads(cache.read_text(encoding="utf-8"));self.vanilla_catalog_status=self.vanilla_catalog_status or f"Vanilla {version}: cache local"
            except Exception:data=None
        if not isinstance(data,list):
            try:
                req=urllib.request.Request(url,headers={"User-Agent":"AlphaQuestEditor/0.9.5"})
                with urllib.request.urlopen(req,timeout=6) as r:raw=r.read()
                data=json.loads(raw.decode("utf-8"));cache.parent.mkdir(parents=True,exist_ok=True);cache.write_bytes(raw)
                self.vanilla_catalog_status=self.vanilla_catalog_status or f"Vanilla {version}: catálogo baixado"
            except Exception as exc:self.errors.append(f"Catálogo vanilla {version}: {exc}");data=[]
        for row in data:
            if isinstance(row,dict) and row.get("name"):
                iid=f"minecraft:{row['name']}";self._ensure_entry(iid,str(row.get("displayName") or ""))
