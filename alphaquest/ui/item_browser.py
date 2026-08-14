from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QListView, QVBoxLayout, QWidget


class _ThumbSignals(QObject):
    loaded = Signal(str, object)


class _ThumbJob(QRunnable):
    """Load PNG bytes outside the GUI thread.

    Opening a ZIP/JAR for every visible icon on the GUI thread was enough for
    Windows to mark large packs as "Not responding". QPixmap creation still
    happens on the GUI thread; only disk/ZIP I/O is moved here.
    """
    def __init__(self, index_ref, item_id: str):
        super().__init__()
        self.index_ref = index_ref
        self.item_id = item_id
        self.signals = _ThumbSignals()

    @Slot()
    def run(self):
        raw = None
        try:
            raw = self.index_ref.get_texture_bytes(self.item_id) if self.index_ref else None
        except Exception:
            raw = None
        self.signals.loaded.emit(self.item_id, raw)


class ItemListModel(QAbstractListModel):
    """Virtual item list with asynchronous, lazy thumbnails."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []
        self.index_ref = None
        self.icon_cache: OrderedDict[str, QIcon] = OrderedDict()
        self.max_icons = 350
        self.pending: set[str] = set()
        self.row_by_id: dict[str, int] = {}
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(4)

    def set_entries(self, entries, index_ref):
        self.beginResetModel()
        self.entries = list(entries)
        self.index_ref = index_ref
        self.row_by_id = {e.item_id: i for i, e in enumerate(self.entries)}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self.entries):
            return None
        e = self.entries[index.row()]
        if role == Qt.DisplayRole:
            return f"{e.display_name}\n{e.item_id}"
        if role == Qt.UserRole:
            return e.item_id
        if role == Qt.ToolTipRole:
            custom = bool(self.index_ref and e.item_id in getattr(self.index_ref,"quest_custom_icon_data",{}))
            role_text = "\nÍcone visual usado por quest/task" if self.index_ref and e.item_id in getattr(self.index_ref,"quest_display_items",set()) else ""
            custom_text = "\nPossui dados/componentes de modelo customizado" if custom else ""
            texture_text = "" if e.texture_ref else "\nPreview indisponível até uma textura/modelo ser localizado"
            return e.item_id + role_text + custom_text + texture_text
        if role == Qt.DecorationRole and self.index_ref:
            icon = self.icon_cache.get(e.item_id)
            if icon is not None:
                self.icon_cache.move_to_end(e.item_id)
                return icon
            if e.item_id not in self.pending:
                self.pending.add(e.item_id)
                job = _ThumbJob(self.index_ref, e.item_id)
                job.signals.loaded.connect(self._thumb_loaded)
                self.pool.start(job)
            return None
        return None

    @Slot(str, object)
    def _thumb_loaded(self, item_id: str, raw):
        self.pending.discard(item_id)
        if raw:
            pix = QPixmap()
            if pix.loadFromData(raw):
                self.icon_cache[item_id] = QIcon(pix)
                self.icon_cache.move_to_end(item_id)
                if len(self.icon_cache) > self.max_icons:
                    self.icon_cache.popitem(last=False)
        row = self.row_by_id.get(item_id)
        if row is not None and 0 <= row < len(self.entries):
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [Qt.DecorationRole])


class ItemBrowser(QWidget):
    itemActivated = Signal(str)
    EMPTY_LIMIT = 600
    SEARCH_LIMIT = 5000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.index = None
        layout = QVBoxLayout(self); layout.setContentsMargins(6,6,6,6)
        self.summary = QLabel("Nenhum índice carregado"); self.summary.setObjectName("mutedText"); layout.addWidget(self.summary)
        row = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText("Buscar por nome ou ID... ex.: mechanical press")
        self.scope = QComboBox(); self.scope.addItems(["Todos","Minecraft","Mods","Ícones Quest"]); row.addWidget(self.search,1); row.addWidget(self.scope); layout.addLayout(row)
        self.list = QListView(); self.list.setUniformItemSizes(True); self.list.setIconSize(QSize(32,32)); self.list.setSpacing(2)
        self.model = ItemListModel(self.list); self.list.setModel(self.model); layout.addWidget(self.list,1)
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(170); self._timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda *_: self._timer.start())
        self.scope.currentTextChanged.connect(lambda *_: self._timer.start())
        self.list.doubleClicked.connect(self._activate)

    def set_index(self,index):
        self.index=index
        if index:
            vanilla=sum(1 for k in index.items if k.startswith("minecraft:")); modded=len(index.items)-vanilla
            source = "cache" if getattr(index, "loaded_from_cache", False) else "índice novo"
            icon_count=len(getattr(index,"quest_display_items",set()))
            self.summary.setText(f"{len(index.items)} itens • {vanilla} Minecraft • {modded} mods • {icon_count} ícones de quest • {source}")
        self.refresh()

    def refresh(self):
        if not self.index:
            self.model.set_entries([], None); return
        scope=self.scope.currentText(); query=self.search.text().strip()
        # Do not materialize the complete registry merely because the Items tab
        # became visible. 600 initial rows are enough to browse; a typed search
        # expands the window while keeping Qt model resets cheap.
        limit = self.SEARCH_LIMIT if query else self.EMPTY_LIMIT
        results = self.index.search(query, limit * (2 if scope in ("Minecraft","Mods","Ícones Quest") else 1))
        if scope=="Minecraft": results=[e for e in results if e.namespace=="minecraft"]
        elif scope=="Mods": results=[e for e in results if e.namespace!="minecraft"]
        elif scope=="Ícones Quest": results=[e for e in results if e.item_id in getattr(self.index,"quest_display_items",set())]
        results=results[:limit]
        self.model.set_entries(results, self.index)
        total=len(self.index.items)
        shown=len(results)
        suffix=f" • mostrando {shown}/{total}" if shown<total and not query else f" • {shown} resultado(s)"
        self.summary.setToolTip(f"{getattr(self.index,'vanilla_catalog_status','')}{suffix}")

    def _activate(self, model_index):
        item_id = model_index.data(Qt.UserRole)
        if item_id: self.itemActivated.emit(item_id)
