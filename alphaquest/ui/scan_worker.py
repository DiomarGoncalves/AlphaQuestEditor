from __future__ import annotations

import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ..core.mod_index import ModIndex


class ModScanWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    cancelled = Signal()
    failed = Signal(str, str)

    def __init__(self, root: Path, force: bool = False, vanilla_jar=None, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.force = bool(force)
        self.vanilla_jar = Path(vanilla_jar) if vanilla_jar else None
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        try:
            index = ModIndex()
            ok = index.scan(
                self.root,
                lambda i, total, name: self.progress.emit(int(i), int(total), str(name)),
                force=self.force,
                minecraft_version="auto",
                cancel_check=self._cancel.is_set,
                vanilla_jar_override=self.vanilla_jar,
            )
            if not ok or self._cancel.is_set():
                self.cancelled.emit()
                return
            self.finished.emit(index)
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())

class AssetSourceScanWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    cancelled = Signal()
    failed = Signal(str, str)

    def __init__(self, sources, kubejs_dir=None, parent=None):
        super().__init__(parent)
        self.sources = [Path(p) for p in sources]
        self.kubejs_dir = Path(kubejs_dir) if kubejs_dir else None
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        try:
            index = ModIndex()
            ok = index.scan_sources(
                self.sources,
                self.kubejs_dir,
                lambda i, total, name: self.progress.emit(int(i), int(total), str(name)),
                cancel_check=self._cancel.is_set,
            )
            if not ok or self._cancel.is_set():
                self.cancelled.emit()
                return
            self.finished.emit(index)
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())
