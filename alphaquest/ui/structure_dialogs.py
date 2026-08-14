from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout


class GroupDialog(QDialog):
    def __init__(self, group=None, parent=None):
        super().__init__(parent); self.group = group
        self.setWindowTitle("Editar grupo" if group else "Novo grupo")
        root=QVBoxLayout(self); form=QFormLayout()
        self.title=QLineEdit(group.title if group else "Novo Grupo")
        self.id=QLineEdit(group.group_id if group else "(gerado automaticamente)")
        self.id.setReadOnly(group is None)
        form.addRow("Nome",self.title); form.addRow("ID",self.id); root.addLayout(form)
        note=QLabel("O ID é o mesmo identificador usado pelo FTB Quests em chapter_groups.snbt."); note.setWordWrap(True); note.setObjectName("mutedText"); root.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
    def value(self): return {"title":self.title.text().strip() or "Grupo", "id": None if self.group is None else self.id.text().strip()}


class ChapterDialog(QDialog):
    def __init__(self, groups, chapter=None, parent=None):
        super().__init__(parent); self.chapter=chapter
        self.setWindowTitle("Editar capítulo" if chapter else "Novo capítulo"); self.resize(500,260)
        root=QVBoxLayout(self); form=QFormLayout()
        self.title=QLineEdit(chapter.title if chapter else "Novo Capítulo")
        self.id=QLineEdit(chapter.chapter_id if chapter else "(gerado automaticamente)"); self.id.setReadOnly(chapter is None)
        self.filename=QLineEdit(chapter.filename if chapter else "novo_capitulo")
        self.group=QComboBox(); self.group.addItem("Sem grupo","")
        for g in groups: self.group.addItem(g.title,g.group_id)
        if chapter:
            idx=self.group.findData(chapter.group_id); self.group.setCurrentIndex(max(0,idx))
        form.addRow("Nome",self.title); form.addRow("ID",self.id); form.addRow("Arquivo",self.filename); form.addRow("Grupo",self.group); root.addLayout(form)
        note=QLabel("Editar o arquivo renomeia o .snbt do capítulo. A criação usa minecraft:book como ícone inicial."); note.setWordWrap(True); note.setObjectName("mutedText"); root.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
    def value(self):
        return {"title":self.title.text().strip() or "Capítulo", "id": None if self.chapter is None else self.id.text().strip(), "filename":self.filename.text().strip(), "group_id":self.group.currentData() or ""}
