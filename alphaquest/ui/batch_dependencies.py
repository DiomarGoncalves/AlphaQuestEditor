from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QRadioButton, QVBoxLayout, QWidget,
)


class BatchDependenciesDialog(QDialog):
    """Apply dependency changes to many quests without touching quest content.

    The dialog intentionally excludes the selected quests from the target list. This
    avoids accidental self-dependencies and the easiest form of circular dependency
    while doing a batch edit. Existing dependencies are preserved when using Add.
    """

    def __init__(self, selected_quests, all_quests, title_provider=None, parent=None):
        super().__init__(parent)
        self.selected_quests = list(selected_quests or [])
        self.all_quests = list(all_quests or [])
        self.title_provider = title_provider or (lambda q: q.title or q.primary_item_id or q.quest_id)
        self.setWindowTitle("Dependências em lote")
        self.resize(720, 650)

        root = QVBoxLayout(self)
        heading = QLabel(f"{len(self.selected_quests)} quests selecionadas")
        heading.setObjectName("panelTitle")
        root.addWidget(heading)
        note = QLabel(
            "Escolha uma ou mais quests-alvo. A operação será aplicada a TODAS as quests selecionadas. "
            "As quests selecionadas ficam ocultas da lista de alvos para evitar auto-dependência/ciclos acidentais."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        modes = QHBoxLayout()
        self.add_mode = QRadioButton("Adicionar dependência")
        self.remove_mode = QRadioButton("Remover dependência")
        self.add_mode.setChecked(True)
        modes.addWidget(self.add_mode)
        modes.addWidget(self.remove_mode)
        modes.addStretch(1)
        root.addLayout(modes)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Pesquisar quest-alvo por nome, item ou ID...")
        root.addWidget(self.search)

        self.list = QListWidget()
        root.addWidget(self.list, 1)

        tools = QHBoxLayout()
        self.check_visible = QPushButton("Marcar visíveis")
        self.clear_checked = QPushButton("Limpar marcações")
        tools.addWidget(self.check_visible)
        tools.addWidget(self.clear_checked)
        tools.addStretch(1)
        self.count_label = QLabel("0 alvos marcados")
        tools.addWidget(self.count_label)
        root.addLayout(tools)

        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        root.addWidget(self.preview)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Aplicar em lote")
        self.ok_button.setEnabled(False)
        root.addWidget(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        self.search.textChanged.connect(self._filter)
        self.list.itemChanged.connect(self._update_state)
        self.add_mode.toggled.connect(self._update_state)
        self.remove_mode.toggled.connect(self._update_state)
        self.check_visible.clicked.connect(self._mark_visible)
        self.clear_checked.clicked.connect(self._clear_checked)

        self._populate()

    def _populate(self):
        selected_ids = {q.quest_id for q in self.selected_quests}
        candidates = [q for q in self.all_quests if q.quest_id and q.quest_id not in selected_ids]
        candidates.sort(key=lambda q: (self.title_provider(q) or q.quest_id).lower())
        self.list.blockSignals(True)
        self.list.clear()
        for q in candidates:
            title = self.title_provider(q) or "Quest sem título"
            extra = q.primary_item_id or ""
            suffix = f" • {extra}" if extra else ""
            item = QListWidgetItem(f"{title}{suffix}   [{q.quest_id}]")
            item.setData(Qt.UserRole, q.quest_id)
            item.setData(Qt.UserRole + 1, f"{title} {extra} {q.quest_id}".lower())
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._update_state()

    def _filter(self, text=""):
        query = (text or "").strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            hay = item.data(Qt.UserRole + 1) or item.text().lower()
            item.setHidden(bool(query and query not in hay))

    def _mark_visible(self):
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.Checked)
        self.list.blockSignals(False)
        self._update_state()

    def _clear_checked(self):
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.Unchecked)
        self.list.blockSignals(False)
        self._update_state()

    def target_ids(self):
        return [
            self.list.item(i).data(Qt.UserRole)
            for i in range(self.list.count())
            if self.list.item(i).checkState() == Qt.Checked
        ]

    def mode(self):
        return "remove" if self.remove_mode.isChecked() else "add"

    def _update_state(self, *_):
        count = len(self.target_ids())
        self.count_label.setText(f"{count} alvo marcado" if count == 1 else f"{count} alvos marcados")
        self.ok_button.setEnabled(count > 0 and bool(self.selected_quests))
        verb = "adicionada a" if self.add_mode.isChecked() else "removida de"
        if count:
            self.preview.setText(
                f"A(s) {count} dependência(s) marcada(s) será(ão) {verb} cada uma das "
                f"{len(self.selected_quests)} quests selecionadas."
            )
        else:
            self.preview.setText("Marque pelo menos uma quest-alvo.")
