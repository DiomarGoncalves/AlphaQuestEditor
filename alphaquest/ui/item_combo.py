from __future__ import annotations

import re
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QComboBox


_ID_AT_END = re.compile(r"\[([^\[\]]+:[^\[\]]+)\]\s*$")


class ItemCombo(QComboBox):
    """Fast, lazy item selector for very large modpacks.

    v0.5 filled every ItemCombo with the complete registry (and decoded every
    icon). Opening a task could therefore construct tens of thousands of Qt
    rows twice (Item + Icon). v0.6 keeps only a small query result window in the
    widget and asks the shared ModIndex as the user types.
    """

    itemIdChanged = Signal(str)
    RESULT_LIMIT = 160

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMaxVisibleItems(18)
        self.setMinimumContentsLength(18)
        self._index = None
        self._updating = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(130)
        self._timer.timeout.connect(self._refresh_suggestions)
        self.lineEdit().textEdited.connect(self._schedule_refresh)
        self.currentIndexChanged.connect(lambda *_: self.itemIdChanged.emit(self.item_id()))

    def set_index(self, index) -> None:
        # Important: NEVER enumerate the entire item registry here.
        current = self.item_id()
        self._index = index
        self._set_rows([], current)

    def _schedule_refresh(self, _text: str) -> None:
        if self._updating:
            return
        self._timer.start()
        self.itemIdChanged.emit(self.item_id())

    def _set_rows(self, entries, typed: str) -> None:
        cursor = self.lineEdit().cursorPosition() if self.lineEdit() else len(typed)
        self._updating = True
        self.blockSignals(True)
        self.clear()
        for e in entries:
            # No icons here on purpose. The grid/catalogue loads thumbnails lazily.
            self.addItem(f"{e.display_name}  [{e.item_id}]", e.item_id)
        self.setCurrentIndex(-1)
        self.setEditText(typed)
        if self.lineEdit():
            self.lineEdit().setCursorPosition(min(cursor, len(typed)))
        self.blockSignals(False)
        self._updating = False

    def _refresh_suggestions(self) -> None:
        if not self._index or self._updating:
            return
        typed = self.currentText().strip()
        # If the visible text is already a formatted exact selection, don't churn.
        m = _ID_AT_END.search(typed)
        query = m.group(1) if m else typed
        entries = self._index.search(query, self.RESULT_LIMIT)
        self._set_rows(entries, typed)
        if typed and self.hasFocus():
            self.showPopup()

    def showPopup(self) -> None:
        # Populate only when the user actually opens the list.
        if self._index and self.count() == 0:
            typed = self.currentText().strip()
            entries = self._index.search(typed, self.RESULT_LIMIT)
            self._set_rows(entries, typed)
        super().showPopup()

    def item_id(self) -> str:
        text = self.currentText().strip()
        m = _ID_AT_END.search(text)
        if m:
            return m.group(1).strip()
        data = self.currentData()
        if data and self.currentIndex() >= 0 and text == self.itemText(self.currentIndex()):
            return str(data)
        if ":" in text and " " not in text:
            return text
        if self._index:
            resolved = self._index.resolve_text(text)
            if resolved:
                return resolved
        return text

    def set_item_id(self, item_id: str) -> None:
        item_id = (item_id or "").strip()
        self._timer.stop()
        if not item_id:
            self._set_rows([], "")
            return
        if self._index and item_id in self._index.items:
            e = self._index.items[item_id]
            self._set_rows([], f"{e.display_name}  [{e.item_id}]")
        else:
            self._set_rows([], item_id)
