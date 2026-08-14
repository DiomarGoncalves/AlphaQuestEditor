from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QListView, QListWidget,
    QMessageBox, QPushButton, QProgressDialog, QTabWidget, QVBoxLayout, QWidget, QLineEdit,
    QApplication,
)

from ..core.mod_index import ModIndex
from .item_browser import ItemBrowser


class ImageListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent); self.entries=[]; self.index_ref=None; self.icons={}

    def set_entries(self, entries, index_ref):
        self.beginResetModel(); self.entries=list(entries); self.index_ref=index_ref; self.icons.clear(); self.endResetModel()

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.entries)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.entries)): return None
        e=self.entries[index.row()]
        if role==Qt.DisplayRole: return f"{e.display_name}\n{e.asset_id}"
        if role==Qt.UserRole: return e.asset_id
        if role==Qt.ToolTipRole:
            src=str(e.source_file) if e.source_file else ""
            return f"{e.asset_id}\n{src}\n{e.internal_path or ''}"
        if role==Qt.DecorationRole and self.index_ref:
            if e.asset_id in self.icons:return self.icons[e.asset_id]
            raw=self.index_ref.get_asset_bytes(e.asset_id)
            if raw:
                p=QPixmap()
                if p.loadFromData(raw):
                    icon=QIcon(p); self.icons[e.asset_id]=icon
                    if len(self.icons)>250:self.icons.pop(next(iter(self.icons)))
                    return icon
        return None


class AssetLibraryDialog(QDialog):
    """Standalone visual scanner for JARs, resource packs and KubeJS.

    It intentionally doesn't require QuestBook/MainWindow.book, so pack authors can
    inspect assets from arbitrary versions before they even have a modpack instance.
    """
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Biblioteca Universal de Assets — JAR / KubeJS"); self.resize(1150,760)
        self.index=ModIndex(); self.sources:list[Path]=[]; self.kubejs_dir:Path|None=None
        root=QVBoxLayout(self); root.setContentsMargins(10,10,10,10); root.setSpacing(8)
        intro=QLabel("Abra JARs, uma pasta de mods ou uma pasta KubeJS sem abrir um modpack. O scanner é independente da versão do Minecraft.")
        intro.setWordWrap(True); intro.setObjectName("mutedText"); root.addWidget(intro)
        row=QHBoxLayout()
        for text,slot in [("＋ JAR(s)",self.add_jars),("＋ Pasta de JARs",self.add_folder),("＋ KubeJS",self.add_kubejs),("Limpar",self.clear_sources),("Indexar",self.scan)]:
            b=QPushButton(text); b.clicked.connect(slot); row.addWidget(b)
        row.addStretch(1); root.addLayout(row)
        self.source_label=QLabel("Nenhuma fonte selecionada"); self.source_label.setObjectName("mutedText"); root.addWidget(self.source_label)
        self.tabs=QTabWidget(); root.addWidget(self.tabs,1)
        self.items=ItemBrowser(); self.tabs.addTab(self.items,"Itens")
        img=QWidget(); il=QVBoxLayout(img); il.setContentsMargins(6,6,6,6)
        self.image_summary=QLabel("Nenhuma imagem indexada"); self.image_summary.setObjectName("mutedText"); il.addWidget(self.image_summary)
        self.image_search=QLineEdit(); self.image_search.setPlaceholderText("Buscar imagem por resource location, namespace ou caminho..."); il.addWidget(self.image_search)
        self.image_view=QListView(); self.image_view.setViewMode(QListView.IconMode); self.image_view.setResizeMode(QListView.Adjust); self.image_view.setMovement(QListView.Static)
        self.image_view.setIconSize(QSize(72,72)); self.image_view.setGridSize(QSize(190,125)); self.image_view.setSpacing(5); self.image_view.setWordWrap(True)
        self.image_model=ImageListModel(self.image_view); self.image_view.setModel(self.image_model); il.addWidget(self.image_view,1); self.tabs.addTab(img,"Imagens / Quest Assets")
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(140); self.timer.timeout.connect(self.refresh_images); self.image_search.textChanged.connect(lambda *_:self.timer.start())
        self.image_view.doubleClicked.connect(self.copy_image_id)

    def add_jars(self):
        files,_=QFileDialog.getOpenFileNames(self,"Selecionar mods/JARs","","Java archives (*.jar *.zip);;Todos (*.*)")
        for f in files:
            p=Path(f)
            if p not in self.sources:self.sources.append(p)
        self._update_sources()

    def add_folder(self):
        d=QFileDialog.getExistingDirectory(self,"Selecionar pasta contendo JARs")
        if d:
            p=Path(d)
            if p not in self.sources:self.sources.append(p)
            self._update_sources()

    def add_kubejs(self):
        d=QFileDialog.getExistingDirectory(self,"Selecionar pasta kubejs (ou pasta que contém assets/startup_scripts)")
        if d:self.kubejs_dir=Path(d);self._update_sources()

    def clear_sources(self):
        self.sources.clear();self.kubejs_dir=None;self.index.clear();self.items.set_index(self.index);self.refresh_images();self._update_sources()

    def _update_sources(self):
        bits=[f"{len(self.sources)} fonte(s) JAR/pasta"]
        if self.kubejs_dir:bits.append(f"KubeJS: {self.kubejs_dir.name}")
        self.source_label.setText(" • ".join(bits) if self.sources or self.kubejs_dir else "Nenhuma fonte selecionada")

    def scan(self):
        if not self.sources and not self.kubejs_dir:return QMessageBox.information(self,"Biblioteca de Assets","Adicione JARs, uma pasta de mods ou uma pasta KubeJS primeiro.")
        dlg=QProgressDialog("Indexando assets...","Cancelar",0,100,self);dlg.setWindowModality(Qt.WindowModal);dlg.setMinimumDuration(100)
        def progress(i,total,name):
            dlg.setLabelText(f"Lendo {name}");dlg.setValue(int(i/max(1,total)*100));QApplication.processEvents()
        self.index.scan_sources(self.sources,self.kubejs_dir,progress);dlg.setValue(100)
        self.items.set_index(self.index);self.refresh_images()
        self.source_label.setText(f"{len(self.index.items)} itens • {len(self.index.images)} imagens • {len(self.index.errors)} aviso(s) • versão independente")

    def refresh_images(self):
        entries=self.index.search_images(self.image_search.text(),10000) if self.index else []
        self.image_model.set_entries(entries,self.index);self.image_summary.setText(f"{len(self.index.images)} imagens indexadas • mostrando {len(entries)}")

    def copy_image_id(self, idx):
        aid=idx.data(Qt.UserRole)
        if aid:
            QApplication.clipboard().setText(aid); self.image_summary.setText(f"Copiado: {aid}")
