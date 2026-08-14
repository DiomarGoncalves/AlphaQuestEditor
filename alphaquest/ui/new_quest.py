from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout
from .item_combo import ItemCombo


class NewQuestDialog(QDialog):
    def __init__(self, item_index=None, x=0.0, y=0.0, parent=None):
        super().__init__(parent); self.setWindowTitle("Nova Quest"); self.resize(520,320)
        root=QVBoxLayout(self); form=QFormLayout()
        self.title=QLineEdit("Nova Quest"); self.task=QComboBox(); self.task.addItems(["item","checkmark","xp","sem task"])
        self.item=ItemCombo(); self.item.set_index(item_index)
        self.count=QSpinBox(); self.count.setRange(1,2_000_000_000); self.count.setValue(1)
        self.x=QDoubleSpinBox(); self.x.setRange(-10000,10000); self.x.setDecimals(3); self.x.setValue(x)
        self.y=QDoubleSpinBox(); self.y.setRange(-10000,10000); self.y.setDecimals(3); self.y.setValue(y)
        for label,w in [("Título",self.title),("Task inicial",self.task),("Item (pesquise nome ou ID)",self.item),("Quantidade / XP",self.count),("X",self.x),("Y",self.y)]: form.addRow(label,w)
        root.addLayout(form); note=QLabel("O editor gera automaticamente IDs válidos para quest/task e cria a chave de tradução pt_br."); note.setWordWrap(True); note.setObjectName("mutedText"); root.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.task.currentTextChanged.connect(self._sync); self._sync()
    def _sync(self):
        t=self.task.currentText(); self.item.setEnabled(t=="item"); self.count.setEnabled(t in ("item","xp"))
    def value(self):
        t=self.task.currentText(); return {"title":self.title.text().strip() or "Nova Quest","task_type":"" if t=="sem task" else t,"item_id":self.item.item_id(),"count":self.count.value(),"x":self.x.value(),"y":self.y.value()}
