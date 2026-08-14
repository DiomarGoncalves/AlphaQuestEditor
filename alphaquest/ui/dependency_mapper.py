from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QRadioButton, QVBoxLayout, QWidget,
)


class DependencyMapperDialog(QDialog):
    """Modeless dependency workbench driven by the current canvas selection.

    The left side stores prerequisite quests (the IDs that will be written into
    ``dependencies``). The right side stores the quests that receive those IDs.
    Keeping both roles explicit removes the usual ambiguity of batch dependency
    editing and supports N-to-M relationships in one operation.
    """

    applyRequested = Signal(list, list, str)  # prerequisite_ids, dependent_ids, mode

    def __init__(self, selection_provider, quest_lookup_provider, title_provider=None, parent=None):
        super().__init__(parent)
        self.selection_provider = selection_provider
        self.quest_lookup_provider = quest_lookup_provider
        self.title_provider = title_provider or (lambda q: q.title or q.primary_item_id or q.quest_id)
        self.prerequisite_ids: list[str] = []
        self.dependent_ids: list[str] = []

        self.setWindowTitle("Mapa de Dependências")
        self.setModal(False)
        self.setWindowModality(Qt.NonModal)
        self.resize(820, 560)

        root = QVBoxLayout(self)
        title = QLabel("Mapa de Dependências")
        title.setObjectName("panelTitle")
        root.addWidget(title)

        help_text = QLabel(
            "1) Selecione no canvas quem precisa ser concluído primeiro e capture como Dependências. "
            "2) Selecione quem deve receber essas dependências e capture como Quem recebe. "
            "3) Confira a prévia e aplique. A relação é adicionada sem apagar dependências existentes."
        )
        help_text.setWordWrap(True)
        root.addWidget(help_text)

        columns = QHBoxLayout()
        self.dep_group, self.dep_list, self.dep_count = self._role_box(
            "1. Dependências (pré-requisitos)",
            "Estas quests precisam ser concluídas primeiro.",
            self._capture_prerequisites,
            self._clear_prerequisites,
        )
        columns.addWidget(self.dep_group, 1)

        arrow_box = QVBoxLayout()
        arrow_box.addStretch(1)
        arrow = QLabel("  →  ")
        arrow.setAlignment(Qt.AlignCenter)
        arrow.setStyleSheet("font-size: 28px; font-weight: 700;")
        arrow_box.addWidget(arrow)
        self.swap_btn = QPushButton("⇄ Trocar lados")
        self.swap_btn.setToolTip("Trocar Dependências e Quem recebe")
        self.swap_btn.clicked.connect(self._swap_roles)
        arrow_box.addWidget(self.swap_btn)
        arrow_box.addStretch(1)
        arrow_widget = QWidget(); arrow_widget.setLayout(arrow_box)
        columns.addWidget(arrow_widget)

        self.recv_group, self.recv_list, self.recv_count = self._role_box(
            "2. Quem recebe (dependentes / codependências)",
            "Estas quests terão os pré-requisitos acima adicionados ao campo dependencies.",
            self._capture_dependents,
            self._clear_dependents,
        )
        columns.addWidget(self.recv_group, 1)
        root.addLayout(columns, 1)

        mode_row = QHBoxLayout()
        self.add_mode = QRadioButton("Adicionar sem substituir")
        self.remove_mode = QRadioButton("Remover esta relação")
        self.add_mode.setChecked(True)
        mode_row.addWidget(self.add_mode)
        mode_row.addWidget(self.remove_mode)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        self.preview.setObjectName("dependencyPreview")
        root.addWidget(self.preview)

        buttons = QHBoxLayout()
        self.capture_deps_btn = QPushButton("Usar seleção → Dependências")
        self.capture_deps_btn.clicked.connect(self._capture_prerequisites)
        self.capture_recv_btn = QPushButton("Usar seleção → Quem recebe")
        self.capture_recv_btn.clicked.connect(self._capture_dependents)
        self.apply_btn = QPushButton("Aplicar relação")
        self.apply_btn.setObjectName("primaryButton")
        self.apply_btn.clicked.connect(self._apply)
        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.hide)
        buttons.addWidget(self.capture_deps_btn)
        buttons.addWidget(self.capture_recv_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.apply_btn)
        buttons.addWidget(close_btn)
        root.addLayout(buttons)

        self.add_mode.toggled.connect(self._refresh)
        self.remove_mode.toggled.connect(self._refresh)
        self._refresh()

    def _role_box(self, title, description, capture_slot, clear_slot):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        note = QLabel(description); note.setWordWrap(True); layout.addWidget(note)
        lst = QListWidget(); layout.addWidget(lst, 1)
        bottom = QHBoxLayout()
        capture = QPushButton("Capturar seleção atual")
        capture.clicked.connect(capture_slot)
        clear = QPushButton("Limpar")
        clear.clicked.connect(clear_slot)
        count = QLabel("0 quests")
        bottom.addWidget(capture)
        bottom.addWidget(clear)
        bottom.addStretch(1)
        bottom.addWidget(count)
        layout.addLayout(bottom)
        return box, lst, count

    def _selected_ids(self) -> list[str]:
        quests = list(self.selection_provider() or [])
        return list(dict.fromkeys(q.quest_id for q in quests if q and q.quest_id))

    def _capture_prerequisites(self):
        ids = self._selected_ids()
        if ids:
            self.prerequisite_ids = ids
            self._refresh()

    def _capture_dependents(self):
        ids = self._selected_ids()
        if ids:
            self.dependent_ids = ids
            self._refresh()

    def _clear_prerequisites(self):
        self.prerequisite_ids = []
        self._refresh()

    def _clear_dependents(self):
        self.dependent_ids = []
        self._refresh()

    def _swap_roles(self):
        self.prerequisite_ids, self.dependent_ids = self.dependent_ids, self.prerequisite_ids
        self._refresh()

    def _quest_lookup(self):
        return self.quest_lookup_provider() or {}

    def _populate(self, widget: QListWidget, ids: list[str]):
        lookup = self._quest_lookup()
        widget.clear()
        for qid in ids:
            q = lookup.get(qid)
            if q is None:
                item = QListWidgetItem(f"Quest não encontrada [{qid}]")
            else:
                title = self.title_provider(q) or "Quest sem título"
                extra = f" • {q.primary_item_id}" if q.primary_item_id else ""
                item = QListWidgetItem(f"{title}{extra}   [{qid}]")
            item.setData(Qt.UserRole, qid)
            widget.addItem(item)

    def _refresh(self):
        self.prerequisite_ids = list(dict.fromkeys(self.prerequisite_ids))
        self.dependent_ids = list(dict.fromkeys(self.dependent_ids))
        self._populate(self.dep_list, self.prerequisite_ids)
        self._populate(self.recv_list, self.dependent_ids)
        self.dep_count.setText(f"{len(self.prerequisite_ids)} quest" if len(self.prerequisite_ids) == 1 else f"{len(self.prerequisite_ids)} quests")
        self.recv_count.setText(f"{len(self.dependent_ids)} quest" if len(self.dependent_ids) == 1 else f"{len(self.dependent_ids)} quests")

        overlap = set(self.prerequisite_ids) & set(self.dependent_ids)
        ready = bool(self.prerequisite_ids and self.dependent_ids and not overlap)
        self.apply_btn.setEnabled(ready)
        if overlap:
            self.preview.setText(
                "⚠ Uma mesma quest está nos dois lados. Remova-a de um dos conjuntos ou use ‘Trocar lados’. "
                "O editor bloqueia auto-dependência."
            )
            return
        if not self.prerequisite_ids or not self.dependent_ids:
            self.preview.setText("Capture os dois lados da relação para habilitar Aplicar.")
            return
        verb = "serão adicionadas a" if self.add_mode.isChecked() else "serão removidas de"
        self.preview.setText(
            f"Prévia: {len(self.prerequisite_ids)} dependência(s) {verb} "
            f"{len(self.dependent_ids)} quest(s) dependente(s). "
            f"Total de relações processadas: {len(self.prerequisite_ids) * len(self.dependent_ids)}."
        )

    def _apply(self):
        self._refresh()
        if not self.apply_btn.isEnabled():
            return
        mode = "remove" if self.remove_mode.isChecked() else "add"
        self.applyRequested.emit(list(self.prerequisite_ids), list(self.dependent_ids), mode)
