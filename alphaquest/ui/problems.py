from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class ProblemsPanel(QWidget):
    problemActivated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.list.itemDoubleClicked.connect(lambda i: self.problemActivated.emit(i.data(Qt.UserRole)))

    def set_problems(self, problems):
        self.list.clear()
        icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}
        for p in problems:
            item = QListWidgetItem(f"{icon.get(p.severity, '•')} {p.message}")
            item.setData(Qt.UserRole, p)
            self.list.addItem(item)
