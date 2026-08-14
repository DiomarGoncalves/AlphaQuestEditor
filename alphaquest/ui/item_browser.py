from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QListView, QVBoxLayout, QWidget


class ItemListModel(QAbstractListModel):
    """Virtual item list: Qt asks data only for visible rows."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []
        self.index_ref = None
        self.icon_cache: OrderedDict[str, QIcon] = OrderedDict()
        self.max_icons = 350

    def set_entries(self, entries, index_ref):
        self.beginResetModel()
        self.entries = list(entries)
        self.index_ref = index_ref
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
            return e.item_id
        if role == Qt.DecorationRole and self.index_ref:
            icon = self.icon_cache.get(e.item_id)
            if icon is not None:
                self.icon_cache.move_to_end(e.item_id)
                return icon
            raw = self.index_ref.get_texture_bytes(e.item_id)
            if raw:
                p = QPixmap()
                if p.loadFromData(raw):
                    icon = QIcon(p)
                    self.icon_cache[e.item_id] = icon
                    if len(self.icon_cache) > self.max_icons:
                        self.icon_cache.popitem(last=False)
                    return icon
        return None


class ItemBrowser(QWidget):
    itemActivated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.index = None
        layout = QVBoxLayout(self); layout.setContentsMargins(6,6,6,6)
        self.summary = QLabel("Nenhum índice carregado"); self.summary.setObjectName("mutedText"); layout.addWidget(self.summary)
        row = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText("Buscar por nome ou ID... ex.: mechanical press")
        self.scope = QComboBox(); self.scope.addItems(["Todos","Minecraft","Mods"]); row.addWidget(self.search,1); row.addWidget(self.scope); layout.addLayout(row)
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
            self.summary.setText(f"{len(index.items)} itens • {vanilla} Minecraft • {modded} mods • {source}")
        self.refresh()

    def refresh(self):
        if not self.index:
            self.model.set_entries([], None); return
        scope=self.scope.currentText()
        # A virtual QListView can handle many rows; filtering is done against the
        # pre-sorted in-memory index without allocating QListWidgetItems.
        results = self.index.search(self.search.text(), 100000)
        if scope=="Minecraft": results=[e for e in results if e.namespace=="minecraft"]
        elif scope=="Mods": results=[e for e in results if e.namespace!="minecraft"]
        self.model.set_entries(results, self.index)
        self.summary.setToolTip(f"Mostrando {len(results)} item(ns). {getattr(self.index,'vanilla_catalog_status','')}")

    def _activate(self, model_index):
        item_id = model_index.data(Qt.UserRole)
        if item_id: self.itemActivated.emit(item_id)
