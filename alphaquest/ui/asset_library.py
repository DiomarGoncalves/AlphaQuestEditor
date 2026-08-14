from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, QRunnable, QSize, Qt, QTimer, QThread, QThreadPool, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QListView,
    QMessageBox, QPushButton, QProgressDialog, QTabWidget, QVBoxLayout, QWidget, QLineEdit,
    QApplication,
)

from ..core.mod_index import ModIndex
from .item_browser import ItemBrowser
from .scan_worker import AssetSourceScanWorker


class _AssetSignals(QObject):
    loaded = Signal(str, object)


class _AssetThumbJob(QRunnable):
    def __init__(self, index_ref, asset_id):
        super().__init__(); self.index_ref=index_ref; self.asset_id=asset_id; self.signals=_AssetSignals()
    @Slot()
    def run(self):
        raw=None
        try: raw=self.index_ref.get_asset_bytes(self.asset_id) if self.index_ref else None
        except Exception: raw=None
        self.signals.loaded.emit(self.asset_id,raw)


class ImageListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent); self.entries=[]; self.index_ref=None; self.icons:OrderedDict[str,QIcon]=OrderedDict(); self.pending=set(); self.row_by_id={}; self.pool=QThreadPool(self); self.pool.setMaxThreadCount(4)

    def set_entries(self, entries, index_ref):
        self.beginResetModel(); self.entries=list(entries); self.index_ref=index_ref; self.row_by_id={e.asset_id:i for i,e in enumerate(self.entries)}; self.endResetModel()

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
            icon=self.icons.get(e.asset_id)
            if icon is not None:
                self.icons.move_to_end(e.asset_id); return icon
            if e.asset_id not in self.pending:
                self.pending.add(e.asset_id); job=_AssetThumbJob(self.index_ref,e.asset_id); job.signals.loaded.connect(self._loaded); self.pool.start(job)
            return None
        return None

    @Slot(str,object)
    def _loaded(self,asset_id,raw):
        self.pending.discard(asset_id)
        if raw:
            p=QPixmap()
            if p.loadFromData(raw):
                self.icons[asset_id]=QIcon(p); self.icons.move_to_end(asset_id)
                if len(self.icons)>250:self.icons.popitem(last=False)
        row=self.row_by_id.get(asset_id)
        if row is not None:
            idx=self.index(row,0); self.dataChanged.emit(idx,idx,[Qt.DecorationRole])


class AssetLibraryDialog(QDialog):
    """Standalone visual scanner for JARs, resource packs and KubeJS."""
    IMAGE_EMPTY_LIMIT=700
    IMAGE_SEARCH_LIMIT=4000

    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Biblioteca Universal de Assets — JAR / KubeJS"); self.resize(1150,760)
        self.index=ModIndex(); self.sources:list[Path]=[]; self.kubejs_dir:Path|None=None; self._scan_thread=None; self._scan_worker=None; self._scan_dialog=None; self._scan_button=None
        root=QVBoxLayout(self); root.setContentsMargins(10,10,10,10); root.setSpacing(8)
        intro=QLabel("Abra JARs, uma pasta de mods ou uma pasta KubeJS sem abrir um modpack. O scanner é independente da versão do Minecraft.")
        intro.setWordWrap(True); intro.setObjectName("mutedText"); root.addWidget(intro)
        row=QHBoxLayout()
        for text,slot in [("＋ JAR(s)",self.add_jars),("＋ Pasta de JARs",self.add_folder),("＋ KubeJS",self.add_kubejs),("Limpar",self.clear_sources),("Indexar",self.scan)]:
            b=QPushButton(text); b.clicked.connect(slot); row.addWidget(b)
            if text=="Indexar": self._scan_button=b
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
        if self._scan_thread is not None and self._scan_thread.isRunning():return
        dlg=QProgressDialog("Indexando assets…","Cancelar",0,100,self);dlg.setWindowModality(Qt.NonModal);dlg.setMinimumDuration(900);dlg.setAutoClose(False);dlg.setAutoReset(False);dlg.setValue(0)
        thread=QThread(self); worker=AssetSourceScanWorker(self.sources,self.kubejs_dir); worker.moveToThread(thread)
        self._scan_thread=thread;self._scan_worker=worker;self._scan_dialog=dlg
        thread.started.connect(worker.run); worker.progress.connect(self._scan_progress,Qt.QueuedConnection); worker.finished.connect(self._scan_finished,Qt.QueuedConnection); worker.cancelled.connect(self._scan_cancelled,Qt.QueuedConnection); worker.failed.connect(self._scan_failed,Qt.QueuedConnection)
        worker.finished.connect(worker.deleteLater); worker.cancelled.connect(worker.deleteLater); worker.failed.connect(worker.deleteLater); worker.finished.connect(thread.quit); worker.cancelled.connect(thread.quit); worker.failed.connect(thread.quit); thread.finished.connect(self._scan_cleanup)
        dlg.canceled.connect(worker.request_cancel)
        if self._scan_button:self._scan_button.setEnabled(False)
        thread.start()

    def _scan_progress(self,i,total,name):
        if self._scan_dialog:
            self._scan_dialog.setLabelText(f"Lendo {name}");self._scan_dialog.setValue(int(i/max(1,total)*100))

    def _scan_finished(self,index):
        self.index=index
        if self._scan_dialog:self._scan_dialog.close()
        self.items.set_index(self.index);self.refresh_images()
        self.source_label.setText(f"{len(self.index.items)} itens • {len(self.index.images)} imagens • {len(self.index.errors)} aviso(s) • versão independente")

    def _scan_cancelled(self):
        if self._scan_dialog:self._scan_dialog.close()
        self.source_label.setText("Indexação cancelada; o índice anterior foi mantido.")

    def _scan_failed(self,message,trace):
        if self._scan_dialog:self._scan_dialog.close()
        QMessageBox.warning(self,"Biblioteca de Assets",f"Falha ao indexar assets.\n\n{message}")

    def _scan_cleanup(self):
        thread=self._scan_thread
        if self._scan_dialog:self._scan_dialog.deleteLater()
        self._scan_dialog=None;self._scan_worker=None;self._scan_thread=None
        if thread:thread.deleteLater()
        if self._scan_button:self._scan_button.setEnabled(True)

    def closeEvent(self,event):
        if self._scan_worker:self._scan_worker.request_cancel()
        if self._scan_thread is not None and self._scan_thread.isRunning():
            self._scan_thread.quit();self._scan_thread.wait(5000)
        super().closeEvent(event)

    def refresh_images(self):
        if not self.index:
            self.image_model.set_entries([],None); return
        query=self.image_search.text().strip(); limit=self.IMAGE_SEARCH_LIMIT if query else self.IMAGE_EMPTY_LIMIT
        entries=self.index.search_images(query,limit)
        self.image_model.set_entries(entries,self.index);self.image_summary.setText(f"{len(self.index.images)} imagens indexadas • mostrando {len(entries)}")

    def copy_image_id(self, idx):
        aid=idx.data(Qt.UserRole)
        if aid:
            QApplication.clipboard().setText(aid); self.image_summary.setText(f"Copiado: {aid}")
