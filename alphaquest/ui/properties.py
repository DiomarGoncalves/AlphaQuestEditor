from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
    QGroupBox, QScrollArea, QSizePolicy, QFrame
)

from ..core.snbt_scan import extract_compound, extract_scalar, extract_string_list
from .item_combo import ItemCombo

TASK_TYPES = ["item", "custom", "xp", "dimension", "stat", "kill", "location", "checkmark", "advancement", "observation", "biome", "structure", "gamestage", "fluid", "forge_energy", "image"]
REWARD_TYPES = ["item", "xp", "xp_levels", "choice", "all_table", "random", "loot", "command", "advancement", "toast", "gamestage", "currency", "custom"]


def _raw_bool(raw: str, key: str) -> bool:
    return extract_scalar(raw or "", key, "false").lower() in ("true", "1", "1b")


def _raw_tri(raw: str, key: str) -> str:
    v = extract_scalar(raw or "", key, "default").lower()
    return v if v in ("default", "true", "false") else "default"


class ComponentDialog(QDialog):
    def __init__(self, kind: str, spec: dict | None = None, item_index=None, parent=None):
        super().__init__(parent)
        self.kind = kind; self.spec = spec or {}; self.item_index = item_index
        self.setWindowTitle("Editar Task" if kind == "task" else "Editar Reward")
        self.resize(610, 590)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.type = QComboBox(); self.type.addItems(TASK_TYPES if kind == "task" else REWARD_TYPES)
        if self.spec.get("type") in [self.type.itemText(i) for i in range(self.type.count())]: self.type.setCurrentText(self.spec.get("type"))
        raw = self.spec.get("raw", "")
        self.title = QLineEdit(self.spec.get("title", ""))
        self.item = ItemCombo(); self.item.set_index(item_index); self.item.set_item_id(self.spec.get("item_id", ""))
        self.amount = QSpinBox(); self.amount.setRange(1, 2_000_000_000); self.amount.setValue(int(self.spec.get("count") or self.spec.get("amount") or 1))
        icon_comp = extract_compound(raw, "icon")
        self.icon = ItemCombo(); self.icon.set_index(item_index); self.icon.set_item_id(self.spec.get("icon_id") or extract_scalar(icon_comp, "id", ""))
        tags = self.spec.get("tags") or extract_string_list(raw, "tags")
        self.tags = QLineEdit(", ".join(tags) if isinstance(tags, list) else str(tags or "")); self.tags.setPlaceholderText("ex.: automation, create")
        form.addRow("Tipo", self.type)
        if kind == "task": form.addRow("Título", self.title)
        form.addRow("Item", self.item); form.addRow("Quantidade / valor", self.amount)
        if kind == "task": form.addRow("Ícone", self.icon); form.addRow("Tags", self.tags)
        root.addLayout(form)

        # Common task options visible in the FTB editor.
        self.task_opts = QWidget(); tf = QFormLayout(self.task_opts); tf.setContentsMargins(0, 4, 0, 4)
        self.optional_task = QCheckBox(); self.optional_task.setChecked(bool(self.spec.get("optional_task", _raw_bool(raw, "optional_task"))))
        self.disable_toast = QCheckBox(); self.disable_toast.setChecked(bool(self.spec.get("disable_toast", _raw_bool(raw, "disable_toast"))))
        tf.addRow("Task opcional", self.optional_task); tf.addRow("Desativar toast de conclusão", self.disable_toast)
        root.addWidget(self.task_opts)

        self.item_opts = QWidget(); inf = QFormLayout(self.item_opts); inf.setContentsMargins(0, 4, 0, 4)
        self.consume_items = QComboBox(); self.consume_items.addItems(["default", "true", "false"]); self.consume_items.setCurrentText(self.spec.get("consume_items") or _raw_tri(raw, "consume_items"))
        self.only_crafting = QComboBox(); self.only_crafting.addItems(["default", "true", "false"]); self.only_crafting.setCurrentText(self.spec.get("only_from_crafting") or _raw_tri(raw, "only_from_crafting"))
        self.match_components = QComboBox(); self.match_components.addItems(["none", "fuzzy", "strict"]); self.match_components.setCurrentText(self.spec.get("match_components") or extract_scalar(raw, "match_components", "none") or "none")
        self.task_screen_only = QCheckBox(); self.task_screen_only.setChecked(bool(self.spec.get("task_screen_only", _raw_bool(raw, "task_screen_only"))))
        inf.addRow("Consumir itens", self.consume_items)
        inf.addRow("Detectar somente por crafting", self.only_crafting)
        inf.addRow("Comparar Data Components", self.match_components)
        inf.addRow("Somente pela Task Screen", self.task_screen_only)
        root.addWidget(self.item_opts)

        self.raw = QTextEdit(self.spec.get("raw", "")); self.raw.setPlaceholderText("SNBT do componente. Tipos ainda sem formulário completo são preservados aqui exatamente.")
        note = QLabel("Item tasks já expõem as opções principais do FTB Quests 2101.1.30. Tipos avançados continuam com SNBT preservado até ganharem formulário próprio.")
        note.setWordWrap(True); note.setObjectName("mutedText"); root.addWidget(note); root.addWidget(self.raw, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.type.currentTextChanged.connect(self._sync); self._sync()

    def _sync(self):
        t = self.type.currentText(); structured = t in ("item", "checkmark", "xp", "xp_levels")
        self.item.setEnabled(t == "item")
        self.icon.setEnabled(self.kind == "task")
        self.tags.setEnabled(self.kind == "task")
        self.title.setEnabled(self.kind == "task")
        self.amount.setEnabled(t in ("item", "xp", "xp_levels", "forge_energy"))
        self.raw.setEnabled(not structured)
        self.task_opts.setVisible(self.kind == "task")
        self.item_opts.setVisible(self.kind == "task" and t == "item")

    def value(self) -> dict:
        t = self.type.currentText()
        return {
            "id": self.spec.get("id", ""), "type": t, "item_id": self.item.item_id(),
            "title": self.title.text().strip() if self.kind == "task" else "",
            "icon_id": self.icon.item_id() if self.kind == "task" else "",
            "tags": [x.strip() for x in self.tags.text().split(",") if x.strip()] if self.kind == "task" else [],
            "count": self.amount.value(), "amount": self.amount.value(),
            "optional_task": self.optional_task.isChecked() if self.kind == "task" else False,
            "disable_toast": self.disable_toast.isChecked() if self.kind == "task" else False,
            "consume_items": self.consume_items.currentText(), "only_from_crafting": self.only_crafting.currentText(),
            "match_components": self.match_components.currentText(), "task_screen_only": self.task_screen_only.isChecked(),
            "raw": self.raw.toPlainText().strip() if t not in ("item", "checkmark", "xp", "xp_levels") else "",
        }


class ComponentList(QWidget):
    changed = Signal()
    def __init__(self, kind: str, parent=None):
        super().__init__(parent); self.kind = kind; self.specs: list[dict] = []; self.item_index = None
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); self.is_dirty = False
        self.list = QListWidget(); self.list.itemDoubleClicked.connect(lambda *_: self.edit_selected()); root.addWidget(self.list)
        row = QHBoxLayout(); self.add = QPushButton("+ Adicionar"); self.edit = QPushButton("Editar"); self.remove = QPushButton("Remover")
        for b in (self.add, self.edit, self.remove): row.addWidget(b)
        row.addStretch(1); root.addLayout(row)
        self.add.clicked.connect(self.add_item); self.edit.clicked.connect(self.edit_selected); self.remove.clicked.connect(self.remove_selected)
    def set_item_index(self, index): self.item_index = index
    def set_specs(self, specs: list[dict]): self.specs = [dict(s) for s in specs]; self.is_dirty = False; self._refresh()
    def _label(self, s):
        extra = s.get("item_id") or (str(s.get("amount") or s.get("count") or "") if s.get("type") in ("xp", "xp_levels", "forge_energy") else "")
        return f"{s.get('type', '?')}  {extra}".strip()
    def _refresh(self):
        self.list.clear()
        for s in self.specs:
            it = QListWidgetItem(self._label(s)); it.setToolTip(s.get("raw", "") or s.get("id", "")); self.list.addItem(it)
    def add_item(self):
        dlg = ComponentDialog(self.kind, item_index=self.item_index, parent=self)
        if dlg.exec(): self.specs.append(dlg.value()); self.is_dirty = True; self._refresh(); self.changed.emit()
    def edit_selected(self):
        row = self.list.currentRow()
        if row < 0: return
        dlg = ComponentDialog(self.kind, self.specs[row], self.item_index, self)
        if dlg.exec(): self.specs[row] = dlg.value(); self.is_dirty = True; self._refresh(); self.changed.emit()
    def remove_selected(self):
        row = self.list.currentRow()
        if row >= 0: self.specs.pop(row); self.is_dirty = True; self._refresh(); self.changed.emit()


class QuestProperties(QWidget):
    saveRequested = Signal(object)
    draftChanged = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent); self.quest = None; self.item_index = None; self._loading = False; self._all_quests = []
        root = QVBoxLayout(self); root.setContentsMargins(10,8,10,8); root.setSpacing(8)
        self.header = QLabel("Nenhuma quest selecionada"); self.header.setObjectName("panelTitle"); self.header.setWordWrap(True); root.addWidget(self.header)
        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)

        # General properties are scrollable and split into sections so smaller screens stay usable.
        general_scroll = QScrollArea(); general_scroll.setWidgetResizable(True); general_scroll.setFrameShape(QFrame.NoFrame)
        general = QWidget(); gl = QVBoxLayout(general); gl.setContentsMargins(8,8,8,8); gl.setSpacing(12)

        self.id = QLineEdit(); self.id.setReadOnly(True)
        self.title = QLineEdit(); self.title.setPlaceholderText("Título da quest em pt_br")
        self.item = ItemCombo()
        self.description = QTextEdit(); self.description.setMinimumHeight(105); self.description.setMaximumHeight(190); self.description.setPlaceholderText("Descrição da quest...")
        self.shape = QComboBox(); self.shape.setEditable(True); self.shape.addItems(["", "circle", "square", "diamond", "hexagon", "octagon"])
        self.size = QDoubleSpinBox(); self.size.setRange(0.1, 8.0); self.size.setSingleStep(.1); self.size.setValue(1.0)
        self.optional = QCheckBox("Ativada"); self.invisible = QCheckBox("Ativada"); self.hide_dependent_lines = QCheckBox("Ativada")
        self.hide_until_complete = QComboBox(); self.hide_until_complete.addItems(["default", "true", "false"])
        self.hide_until_visible = QComboBox(); self.hide_until_visible.addItems(["default", "true", "false"])
        self.hide_dep_lines = QComboBox(); self.hide_dep_lines.addItems(["default", "true", "false"])
        self.sequential = QComboBox(); self.sequential.addItems(["default", "true", "false"])
        self.repeat = QComboBox(); self.repeat.addItems(["default", "true", "false"])
        self.min_deps = QSpinBox(); self.min_deps.setRange(0, 999)

        for w in (self.id,self.title,self.item,self.shape,self.size,self.hide_until_complete,self.hide_until_visible,self.hide_dep_lines,self.sequential,self.repeat,self.min_deps):
            w.setMinimumHeight(34)
            w.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)

        def section(title, rows):
            box=QGroupBox(title); form=QFormLayout(box); form.setContentsMargins(12,16,12,12); form.setHorizontalSpacing(18); form.setVerticalSpacing(10); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow); form.setLabelAlignment(Qt.AlignLeft|Qt.AlignVCenter)
            for label,widget in rows: form.addRow(label,widget)
            gl.addWidget(box)
            return box

        section("Informações",[("ID",self.id),("Título pt_br",self.title),("Item principal",self.item),("Descrição",self.description)])
        section("Aparência",[("Shape",self.shape),("Tamanho",self.size)])
        section("Comportamento",[("Opcional",self.optional),("Invisível",self.invisible),("Tasks sequenciais",self.sequential),("Pode repetir",self.repeat)])
        section("Visibilidade e dependências",[("Ocultar linhas dependentes",self.hide_dependent_lines),("Ocultar até deps completas",self.hide_until_complete),("Ocultar até deps visíveis",self.hide_until_visible),("Ocultar linhas de dependência",self.hide_dep_lines),("Mínimo de dependências",self.min_deps)])
        self.live_status = QLabel(""); self.live_status.setWordWrap(True); self.live_status.setObjectName("liveStatus"); gl.addWidget(self.live_status); gl.addStretch(1)
        general_scroll.setWidget(general); self.tabs.addTab(general_scroll, "Geral")

        deps = QWidget(); dl = QVBoxLayout(deps); dl.setContentsMargins(8,8,8,8); dl.setSpacing(8)
        self.dep_search = QLineEdit(); self.dep_search.setMinimumHeight(36); self.dep_search.setPlaceholderText("Pesquisar dependência por nome ou ID...")
        dl.addWidget(self.dep_search); dl.addWidget(QLabel("Marque as quests que esta quest depende:")); self.dep_list = QListWidget(); dl.addWidget(self.dep_list); self.tabs.addTab(deps, "Dependências")
        self.dep_search.textChanged.connect(self._filter_deps)
        self.tasks = ComponentList("task"); self.tabs.addTab(self.tasks, "Tasks")
        self.rewards = ComponentList("reward"); self.tabs.addTab(self.rewards, "Rewards")

        row = QHBoxLayout(); self.save = QPushButton("Salvar quest"); self.save.setObjectName("primaryButton"); self.save.setMinimumHeight(40); row.addStretch(1); row.addWidget(self.save); root.addLayout(row)
        self.save.clicked.connect(self._save); self.title.textChanged.connect(self._draft); self.item.itemIdChanged.connect(lambda *_: self._draft()); self.setEnabled(False)

    def set_item_index(self, index):
        self.item_index = index; self.item.set_index(index); self.tasks.set_item_index(index); self.rewards.set_item_index(index); self._validate_item()

    def set_shapes(self, shape_ids):
        current = self.shape.currentText(); vals = [""] + sorted(set(shape_ids)); self.shape.clear(); self.shape.addItems(vals); self.shape.setCurrentText(current)

    def set_all_quests(self, quests): self._all_quests = list(quests); self._rebuild_deps()

    def _rebuild_deps(self):
        self.dep_list.clear()
        if not self.quest: return
        for q in self._all_quests:
            if q.quest_id == self.quest.quest_id: continue
            label = q.title or q.primary_item_id or q.quest_id
            it = QListWidgetItem(f"{label}   [{q.quest_id}]"); it.setData(Qt.UserRole, q.quest_id); it.setData(Qt.UserRole + 1, f"{label} {q.quest_id}".lower()); it.setFlags(it.flags() | Qt.ItemIsUserCheckable); it.setCheckState(Qt.Checked if q.quest_id in self.quest.dependencies else Qt.Unchecked); self.dep_list.addItem(it)
        self._filter_deps(self.dep_search.text())

    def _filter_deps(self, text=""):
        q = (text or "").strip().lower()
        for i in range(self.dep_list.count()):
            it = self.dep_list.item(i); hay = it.data(Qt.UserRole + 1) or it.text().lower(); it.setHidden(bool(q and q not in hay))

    def set_quest(self, q):
        self.quest = q; self.setEnabled(q is not None)
        if not q: return
        self._loading = True; self.header.setText(q.title or "Quest"); self.id.setText(q.quest_id); self.title.setText(q.title); self.item.set_item_id(q.primary_item_id); self.description.setPlainText(q.description)
        self.shape.setCurrentText(q.shape or ""); self.size.setValue(q.size or 1.0); self.optional.setChecked(q.optional); self.invisible.setChecked(q.invisible); self.hide_dependent_lines.setChecked(q.hide_dependent_lines)
        self.hide_until_complete.setCurrentText(q.hide_until_deps_complete or "default"); self.hide_until_visible.setCurrentText(q.hide_until_deps_visible or "default"); self.hide_dep_lines.setCurrentText(q.hide_dependency_lines or "default"); self.sequential.setCurrentText(q.require_sequential_tasks or "default"); self.repeat.setCurrentText(q.can_repeat or "default"); self.min_deps.setValue(q.min_required_dependencies)
        self.tasks.set_specs([{"id": t.task_id, "type": t.task_type, "item_id": t.item_id, "count": t.count, "title": t.title, "raw": t.raw} for t in q.tasks])
        self.rewards.set_specs([{"id": r.reward_id, "type": r.reward_type, "item_id": r.item_id, "count": r.count, "amount": r.amount, "raw": r.raw} for r in q.rewards])
        self._rebuild_deps(); self._loading = False; self._validate_item()

    def set_item(self, item_id):
        if self.quest: self.item.set_item_id(item_id)
    def focus_title(self): self.tabs.setCurrentIndex(0); self.title.setFocus(); self.title.selectAll()
    def focus_description(self): self.tabs.setCurrentIndex(0); self.description.setFocus()
    def focus_general(self): self.tabs.setCurrentIndex(0); self.title.setFocus()

    def _draft(self):
        if self._loading: return
        self._validate_item(); self.draftChanged.emit(self.title.text().strip(), self.item.item_id())
    def _validate_item(self):
        item_id = self.item.item_id()
        if not item_id: self.live_status.setText("🟡 Sem item principal (válido para quests subjetivas)."); self.item.setStyleSheet(""); return
        if self.item_index and item_id in self.item_index.items:
            self.live_status.setText(f"🟢 {self.item_index.items[item_id].display_name} — item encontrado"); self.item.setStyleSheet("QComboBox{border:1px solid #4caf50;}")
        elif self.item_index: self.live_status.setText("🔴 Item não encontrado no índice de Minecraft/modpack."); self.item.setStyleSheet("QComboBox{border:1px solid #ef5350;}")

    def _save(self):
        if not self.quest: return
        deps = [self.dep_list.item(i).data(Qt.UserRole) for i in range(self.dep_list.count()) if self.dep_list.item(i).checkState() == Qt.Checked]
        self.saveRequested.emit({
            "title": self.title.text().strip(), "description": self.description.toPlainText(), "item_id": self.item.item_id(), "shape": self.shape.currentText().strip(), "size": self.size.value(), "optional": self.optional.isChecked(), "invisible": self.invisible.isChecked(), "hide_dependent_lines": self.hide_dependent_lines.isChecked(), "hide_until_deps_complete": self.hide_until_complete.currentText(), "hide_until_deps_visible": self.hide_until_visible.currentText(), "hide_dependency_lines": self.hide_dep_lines.currentText(), "require_sequential_tasks": self.sequential.currentText(), "can_repeat": self.repeat.currentText(), "min_required_dependencies": self.min_deps.value(), "dependencies": deps, "tasks": self.tasks.specs, "rewards": self.rewards.specs, "tasks_dirty": self.tasks.is_dirty, "rewards_dirty": self.rewards.is_dirty
        })
