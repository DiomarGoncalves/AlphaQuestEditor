from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from .models import ItemEntry


VANILLA_VERSION = "1.21.1"
VANILLA_DATA_URL = "https://raw.githubusercontent.com/PrismarineJS/minecraft-data/master/data/pc/1.21.1/items.json"
CACHE_VERSION = 3


@dataclass(slots=True)
class _JarAssets:
    path: Path
    names: set[str]
    json_cache: dict[str, dict]
    lang: dict[str, str]


class ModIndex:
    """Offline-first item catalogue optimized for large modpacks.

    v0.6 deliberately separates *indexing* from *thumbnail decoding*:
    - JARs are scanned once and persisted in `.alphaquest/cache/item_index_v3.json`.
    - Item PNG bytes are NOT loaded for every registry entry during indexing.
    - Thumbnails are opened lazily only for rows currently visible on screen.
    - Search uses one pre-sorted shared list rather than sorting the whole registry
      every time a Task/Reward dialog opens.
    """

    def __init__(self) -> None:
        self.items: dict[str, ItemEntry] = {}
        self._jar_assets: list[_JarAssets] = []
        self.errors: list[str] = []
        self.quest_shapes: dict[str, bytes] = {}
        self.vanilla_catalog_status = ""
        self.loaded_from_cache = False
        self._sorted_items: list[ItemEntry] = []
        self._search_rows: list[tuple[str, ItemEntry]] = []
        self._display_exact: dict[str, str | None] = {}
        self._texture_cache: OrderedDict[str, bytes | None] = OrderedDict()
        self._texture_cache_limit = 550
        self._root: Path | None = None

    def clear(self) -> None:
        self.items.clear(); self._jar_assets.clear(); self.errors.clear(); self.quest_shapes.clear()
        self.vanilla_catalog_status = ""; self.loaded_from_cache = False
        self._sorted_items.clear(); self._search_rows.clear(); self._display_exact.clear(); self._texture_cache.clear()

    # ------------------------------------------------------------------
    # Persistent cache / fingerprint
    # ------------------------------------------------------------------
    def _cache_path(self, root: Path) -> Path:
        return root / ".alphaquest" / "cache" / "item_index_v3.json"

    @staticmethod
    def _stat_token(path: Path, base: Path | None = None) -> tuple[str, int, int]:
        st = path.stat()
        try:
            name = path.relative_to(base).as_posix() if base else str(path.resolve())
        except Exception:
            name = str(path.resolve())
        return name, int(st.st_size), int(st.st_mtime_ns)

    def _fingerprint(self, root: Path, vanilla_jar: Path | None = None) -> list[tuple[str, int, int]]:
        rows: list[tuple[str, int, int]] = []
        mods = root / "mods"
        if mods.exists():
            for p in sorted(mods.glob("*.jar")):
                try: rows.append(self._stat_token(p, root))
                except OSError: pass
        if vanilla_jar and vanilla_jar.exists():
            try: rows.append(self._stat_token(vanilla_jar, None))
            except OSError: pass
        # Scripted/KubeJS items must invalidate the cache too. We intentionally
        # fingerprint metadata only, not file contents, to keep startup cheap.
        kube = root / "kubejs"
        if kube.exists():
            for pat in ("**/*.js", "assets/**/textures/item/*.png", "assets/**/lang/*.json"):
                for p in sorted(kube.glob(pat)):
                    if p.is_file():
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
            if data.get("version") != CACHE_VERSION or data.get("fingerprint") != [list(x) for x in fingerprint]:
                return False
            self.items.clear()
            for row in data.get("items", []):
                item_id = row.get("item_id", "")
                if ":" not in item_id: continue
                ns, rel = item_id.split(":", 1)
                self.items[item_id] = ItemEntry(
                    item_id=item_id, namespace=ns, path=rel,
                    display_name=row.get("display_name") or rel.replace("_", " ").title(),
                    texture_bytes=None,
                    source_jar=self._path_from_cache(row.get("source"), root),
                    model_path=row.get("model_path"), texture_ref=row.get("texture_ref"),
                )
            self.quest_shapes = {
                k: base64.b64decode(v) for k, v in (data.get("quest_shapes") or {}).items() if isinstance(v, str)
            }
            self.vanilla_catalog_status = data.get("vanilla_catalog_status", "")
            self.loaded_from_cache = True
            self._finalize_search_index()
            return bool(self.items)
        except Exception as exc:
            self.errors.append(f"Cache de itens ignorado: {exc}")
            return False

    def _save_cache(self, root: Path, fingerprint) -> None:
        p = self._cache_path(root)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": CACHE_VERSION,
                "fingerprint": [list(x) for x in fingerprint],
                "vanilla_catalog_status": self.vanilla_catalog_status,
                "items": [{
                    "item_id": e.item_id,
                    "display_name": e.display_name,
                    "source": self._path_for_cache(e.source_jar, root),
                    "model_path": e.model_path,
                    "texture_ref": e.texture_ref,
                } for e in self._sorted_items],
                "quest_shapes": {k: base64.b64encode(v).decode("ascii") for k, v in self.quest_shapes.items()},
            }
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            tmp.replace(p)
        except Exception as exc:
            self.errors.append(f"Não foi possível salvar cache do índice: {exc}")

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------
    def scan(self, modpack_root: Path, progress=None, force: bool = False) -> None:
        self.clear(); self._root = modpack_root
        mods_dir = modpack_root / "mods"
        jars = sorted(mods_dir.glob("*.jar")) if mods_dir.exists() else []
        vanilla_jar = self._find_vanilla_client_jar(modpack_root)
        fingerprint = self._fingerprint(modpack_root, vanilla_jar)
        if not force and self._load_cache(modpack_root, fingerprint):
            if progress: progress(1, 1, "Cache de itens")
            return

        scan_jars = list(jars)
        if vanilla_jar and vanilla_jar not in scan_jars:
            scan_jars.insert(0, vanilla_jar)
        total = max(1, len(scan_jars) + 2)
        for idx, jar in enumerate(scan_jars, 1):
            try: self._scan_jar(jar)
            except Exception as exc: self.errors.append(f"{jar.name}: {exc}")
            if progress: progress(idx, total, jar.name)
        self._build_entries()
        # Zip name sets and parsed model caches can be large on big modpacks; after
        # the registry has been built they are dead weight. Keep only compact item
        # entries + lazy source references so the editor stays light while editing.
        self._jar_assets.clear()
        if progress: progress(len(scan_jars) + 1, total, "Catálogo vanilla 1.21.1")
        self._seed_vanilla_catalog(modpack_root)
        self._scan_loose_resources(modpack_root)
        self._finalize_search_index()
        if progress: progress(len(scan_jars) + 2, total, "Salvando cache")
        self._save_cache(modpack_root, fingerprint)

    def _find_vanilla_client_jar(self, root: Path) -> Path | None:
        candidates: list[Path] = []
        bases = [root, *list(root.parents)[:4]]
        home = Path.home(); appdata = os.environ.get("APPDATA"); localapp = os.environ.get("LOCALAPPDATA")
        if appdata: bases += [Path(appdata) / ".minecraft", Path(appdata) / "PrismLauncher", Path(appdata) / "MultiMC"]
        if localapp: bases += [Path(localapp) / "Packages"]
        bases += [home / ".minecraft", home / "AppData" / "Roaming" / ".minecraft", home / "AppData" / "Roaming" / "PrismLauncher"]
        for base in bases:
            candidates.extend([
                base / "versions" / VANILLA_VERSION / f"{VANILLA_VERSION}.jar",
                base / ".minecraft" / "versions" / VANILLA_VERSION / f"{VANILLA_VERSION}.jar",
                base / "libraries" / "com" / "mojang" / "minecraft" / VANILLA_VERSION / f"minecraft-{VANILLA_VERSION}-client.jar",
                base / "libraries" / "com" / "mojang" / "minecraft" / VANILLA_VERSION / f"minecraft-{VANILLA_VERSION}.jar",
            ])
        for p in candidates:
            if p.exists() and p.is_file():
                self.vanilla_catalog_status = f"Minecraft local: {p.name}"; return p
        for base in [root.parent, root.parent.parent if root.parent != root else root]:
            if not base.exists(): continue
            for pat in [f"libraries/com/mojang/minecraft/{VANILLA_VERSION}/*client*.jar", f"versions/{VANILLA_VERSION}/{VANILLA_VERSION}.jar"]:
                found = next(base.glob(pat), None)
                if found and found.is_file(): self.vanilla_catalog_status = f"Minecraft local: {found.name}"; return found
        return None

    def _seed_vanilla_catalog(self, root: Path) -> None:
        cache = root / ".alphaquest" / "cache" / f"vanilla_items_{VANILLA_VERSION}.json"
        data = None
        if cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8")); self.vanilla_catalog_status = self.vanilla_catalog_status or "Vanilla 1.21.1: cache local"
            except Exception: data = None
        if not isinstance(data, list):
            try:
                req = urllib.request.Request(VANILLA_DATA_URL, headers={"User-Agent": "AlphaQuestEditor/0.6"})
                with urllib.request.urlopen(req, timeout=6) as r: raw = r.read()
                data = json.loads(raw.decode("utf-8")); cache.parent.mkdir(parents=True, exist_ok=True); cache.write_bytes(raw)
                self.vanilla_catalog_status = self.vanilla_catalog_status or "Vanilla 1.21.1: catálogo baixado e cacheado"
            except Exception as exc:
                self.errors.append(f"Catálogo vanilla 1.21.1 não pôde ser baixado: {exc}"); data = []
                self.vanilla_catalog_status = self.vanilla_catalog_status or "Vanilla 1.21.1: catálogo remoto indisponível"
        for row in data:
            if not isinstance(row, dict) or not row.get("name"): continue
            item_id = f"minecraft:{row['name']}"
            if item_id in self.items: continue
            self.items[item_id] = ItemEntry(item_id=item_id, namespace="minecraft", path=str(row["name"]), display_name=str(row.get("displayName") or row["name"].replace("_", " ").title()))

    def _scan_jar(self, jar: Path) -> None:
        with zipfile.ZipFile(jar) as zf:
            names = set(zf.namelist()); cache: dict[str, dict] = {}; lang: dict[str, str] = {}
            for locale in ("en_us", "pt_br"):
                suffix = f"/lang/{locale}.json"
                for name in names:
                    if not name.startswith("assets/") or not name.endswith(suffix): continue
                    try:
                        data = json.loads(zf.read(name).decode("utf-8"))
                        if locale == "en_us":
                            for k, v in data.items(): lang.setdefault(k, str(v))
                        else:
                            for k, v in data.items(): lang[k] = str(v)
                    except Exception: continue
            for name in names:
                if name.startswith("assets/") and "/textures/shapes/" in name and name.endswith("/shape.png"):
                    try:
                        shape_id = name.split("/textures/shapes/", 1)[1].rsplit("/shape.png", 1)[0]
                        if shape_id: self.quest_shapes.setdefault(shape_id, zf.read(name))
                    except Exception: pass
            self._jar_assets.append(_JarAssets(jar, names, cache, lang))

    @staticmethod
    def _json(assets: _JarAssets, zf: zipfile.ZipFile, path: str) -> dict:
        if path in assets.json_cache: return assets.json_cache[path]
        try:
            data = json.loads(zf.read(path).decode("utf-8")); data = data if isinstance(data, dict) else {}
        except Exception: data = {}
        assets.json_cache[path] = data; return data

    def _candidate_ids_from_data(self, assets: _JarAssets, zf: zipfile.ZipFile) -> set[str]:
        ids: set[str] = set(); id_re = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
        for name in assets.names:
            if not (name.startswith("data/") and ("/tags/item/" in name or "/tags/items/" in name) and name.endswith(".json")): continue
            data = self._json(assets, zf, name)
            for v in data.get("values", []) if isinstance(data.get("values"), list) else []:
                if isinstance(v, str) and not v.startswith("#") and id_re.match(v): ids.add(v)
                elif isinstance(v, dict) and isinstance(v.get("id"), str) and id_re.match(v["id"]): ids.add(v["id"])
        for name in assets.names:
            if not (name.startswith("data/") and ("/recipe/" in name or "/recipes/" in name) and name.endswith(".json")): continue
            data = self._json(assets, zf, name)
            def walk(x):
                if isinstance(x, dict):
                    for k, v in x.items():
                        if k in ("item", "id") and isinstance(v, str) and id_re.match(v): ids.add(v)
                        else: walk(v)
                elif isinstance(x, list):
                    for v in x: walk(v)
            walk(data)
        return ids

    def _ensure_entry(self, item_id: str, display: str = "", source: Path | None = None, texture_ref: str | None = None, model_path: str | None = None) -> None:
        if ":" not in item_id or item_id.startswith("#"): return
        ns, rel = item_id.split(":", 1); existing = self.items.get(item_id)
        if existing:
            if texture_ref and not existing.texture_ref: existing.texture_ref = texture_ref
            if source and not existing.source_jar: existing.source_jar = source
            if model_path and not existing.model_path: existing.model_path = model_path
            if display and (not existing.display_name or existing.display_name == existing.path.replace("_", " ").title()): existing.display_name = display
            return
        self.items[item_id] = ItemEntry(item_id=item_id, namespace=ns, path=rel, display_name=display or rel.replace("/", " ").replace("_", " ").title(), source_jar=source, model_path=model_path, texture_ref=texture_ref)

    def _build_entries(self) -> None:
        for assets in self._jar_assets:
            try:
                with zipfile.ZipFile(assets.path) as zf:
                    for model in [n for n in assets.names if n.startswith("assets/") and "/models/item/" in n and n.endswith(".json")]:
                        parts = model.split("/")
                        if len(parts) < 5: continue
                        ns = parts[1]; rel = model.split("/models/item/", 1)[1][:-5]; item_id = f"{ns}:{rel}"
                        texture_ref = self._resolve_item_texture_ref(assets, zf, ns, model)
                        display = assets.lang.get(f"item.{ns}.{rel.replace('/', '.')}", "") or assets.lang.get(f"block.{ns}.{rel.replace('/', '.')}", "")
                        self._ensure_entry(item_id, display, assets.path, texture_ref, model)
                    for tex in [n for n in assets.names if n.startswith("assets/") and "/textures/item/" in n and n.endswith(".png")]:
                        ns = tex.split("/")[1]; rel = tex.split("/textures/item/", 1)[1][:-4]
                        display = assets.lang.get(f"item.{ns}.{rel.replace('/', '.')}", "")
                        self._ensure_entry(f"{ns}:{rel}", display, assets.path, f"{ns}:item/{rel}")
                    for lang_key, display in assets.lang.items():
                        kind = "item." if lang_key.startswith("item.") else ("block." if lang_key.startswith("block.") else "")
                        if not kind: continue
                        bits = lang_key.split(".", 2)
                        if len(bits) != 3: continue
                        _, ns, rel_key = bits; rel = rel_key.replace(".", "/"); texture_ref = None
                        for direct, ref in [(f"assets/{ns}/textures/item/{rel}.png", f"{ns}:item/{rel}"), (f"assets/{ns}/textures/block/{rel}.png", f"{ns}:block/{rel}")]:
                            if direct in assets.names: texture_ref = ref; break
                        self._ensure_entry(f"{ns}:{rel}", str(display), assets.path, texture_ref)
                    for item_id in self._candidate_ids_from_data(assets, zf):
                        ns, rel = item_id.split(":", 1)
                        display = assets.lang.get(f"item.{ns}.{rel.replace('/', '.')}", "") or assets.lang.get(f"block.{ns}.{rel.replace('/', '.')}", "")
                        self._ensure_entry(item_id, display, assets.path)
            except Exception as exc:
                self.errors.append(f"{assets.path.name}: {exc}")

    def _scan_loose_resources(self, root: Path) -> None:
        for base in [root / "kubejs" / "assets", root / "resourcepacks"]:
            if not base.exists(): continue
            try:
                for p in base.rglob("textures/item/*.png"):
                    parts = p.parts
                    try: ai = parts.index("assets"); ns = parts[ai + 1]
                    except Exception: continue
                    rel = p.relative_to(Path(*parts[:ai + 2]) / "textures" / "item").with_suffix("").as_posix()
                    self._ensure_entry(f"{ns}:{rel}", source=p, texture_ref="file")
            except Exception as exc: self.errors.append(f"Assets soltos: {exc}")
        scripts = root / "kubejs"
        if scripts.exists():
            pat = re.compile(r"(?:event\.create|create)\(\s*['\"]([a-z0-9_.-]+:[a-z0-9_./-]+)['\"]", re.I)
            for p in scripts.rglob("*.js"):
                try: text = p.read_text(encoding="utf-8", errors="ignore")
                except Exception: continue
                for m in pat.finditer(text): self._ensure_entry(m.group(1).lower(), source=p)

    def _resolve_item_texture_ref(self, assets: _JarAssets, zf: zipfile.ZipFile, ns: str, model_path: str) -> str | None:
        visited: set[str] = set()
        def resolve(path: str, depth: int = 0) -> str | None:
            if depth > 10 or path in visited or path not in assets.names: return None
            visited.add(path); data = self._json(assets, zf, path); textures = data.get("textures") if isinstance(data.get("textures"), dict) else {}
            candidates = []
            for key in ("layer0", "particle", "all", "side", "front", "top"):
                if key in textures: candidates.append(textures[key])
            candidates.extend(v for v in textures.values() if v not in candidates)
            for ref in candidates:
                if not isinstance(ref, str) or ref.startswith("#"): continue
                tns, tpath = (ref.split(":", 1) if ":" in ref else (ns, ref)); png = f"assets/{tns}/textures/{tpath}.png"
                if png in assets.names: return f"{tns}:{tpath}"
            parent = data.get("parent")
            if isinstance(parent, str) and parent not in ("item/generated", "item/handheld", "builtin/entity"):
                pns, ppath = (parent.split(":", 1) if ":" in parent else (ns, parent))
                return resolve(f"assets/{pns}/models/{ppath}.json", depth + 1)
            return None
        return resolve(model_path)

    # ------------------------------------------------------------------
    # Fast lookup / lazy textures
    # ------------------------------------------------------------------
    def _finalize_search_index(self) -> None:
        self._sorted_items = sorted(self.items.values(), key=lambda x: (x.namespace != "minecraft", x.namespace, x.display_name.casefold(), x.item_id))
        self._search_rows = [(f"{e.display_name} {e.item_id}".casefold(), e) for e in self._sorted_items]
        self._display_exact.clear()
        for e in self._sorted_items:
            key = e.display_name.strip().casefold()
            if not key: continue
            if key not in self._display_exact: self._display_exact[key] = e.item_id
            elif self._display_exact[key] != e.item_id: self._display_exact[key] = None

    def search(self, text: str, limit: int = 1000) -> list[ItemEntry]:
        if not self._sorted_items and self.items: self._finalize_search_index()
        q = (text or "").strip().casefold(); limit = max(1, int(limit))
        if not q: return self._sorted_items[:limit]
        out: list[ItemEntry] = []
        # Multiple words can match in any order: "press create" works too.
        tokens = [t for t in q.split() if t]
        for hay, e in self._search_rows:
            if all(t in hay for t in tokens):
                out.append(e)
                if len(out) >= limit: break
        return out

    def resolve_text(self, text: str) -> str:
        text = (text or "").strip()
        if text in self.items: return text
        return self._display_exact.get(text.casefold()) or ""

    def get_texture_bytes(self, item_id: str) -> bytes | None:
        if not item_id: return None
        if item_id in self._texture_cache:
            raw = self._texture_cache.pop(item_id); self._texture_cache[item_id] = raw; return raw
        e = self.items.get(item_id); raw = None
        if e:
            if e.texture_bytes: raw = e.texture_bytes
            elif e.source_jar and e.source_jar.exists():
                try:
                    if e.source_jar.suffix.lower() == ".jar" and e.texture_ref and ":" in e.texture_ref:
                        ns, rel = e.texture_ref.split(":", 1)
                        internal = f"assets/{ns}/textures/{rel}.png"
                        with zipfile.ZipFile(e.source_jar) as zf:
                            raw = zf.read(internal) if internal in zf.namelist() else None
                    elif e.source_jar.suffix.lower() == ".png":
                        raw = e.source_jar.read_bytes()
                except Exception:
                    raw = None
        self._texture_cache[item_id] = raw
        if len(self._texture_cache) > self._texture_cache_limit:
            self._texture_cache.popitem(last=False)
        return raw
