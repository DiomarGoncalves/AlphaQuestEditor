from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.translation_report import export_translation_report, import_translation_report


class TranslationEditor(QWidget):
    saveRequested = Signal(object)    # list[(key, pt, en)]
    importRequested = Signal(object)  # list[dict(key, pt_br, en_us)]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.book = None
        self._loading = False

        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Pesquisar chave, nome ou texto...")
        self.missing = QCheckBox("Somente ausentes")
        self.summary = QLabel("")
        bar.addWidget(self.search, 1); bar.addWidget(self.missing); bar.addWidget(self.summary)
        root.addLayout(bar)

        actions = QHBoxLayout()
        self.export_btn = QPushButton("Exportar relatório")
        self.export_btn.setToolTip("Exporta as linhas atualmente visíveis. Use 'Somente ausentes' para gerar um arquivo só com lacunas.")
        self.import_btn = QPushButton("Importar relatório")
        self.import_btn.setToolTip("Importa CSV/JSON exportado pelo Alpha Quest Editor. Células vazias preservam o texto existente.")
        self.save = QPushButton("Salvar traduções")
        actions.addWidget(self.export_btn); actions.addWidget(self.import_btn); actions.addStretch(1); actions.addWidget(self.save)
        root.addLayout(actions)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Chave", "Português (pt_br)", "English (en_us)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setDefaultSectionSize(42)
        root.addWidget(self.table)

        self.search.textChanged.connect(self._filter)
        self.missing.toggled.connect(self._filter)
        self.save.clicked.connect(self._save)
        self.export_btn.clicked.connect(self._export_report)
        self.import_btn.clicked.connect(self._import_report)

    def set_book(self, book):
        self.book = book
        self.reload()

    def reload(self):
        self._loading = True
        self.table.setRowCount(0)
        if not self.book:
            self._loading = False
            self.summary.setText("")
            return
        keys = set(self.book.lang_pt) | set(self.book.lang_en)
        # Add all expected quest/chapter keys even if the language file is incomplete.
        for ch in self.book.chapters:
            if ch.title_key:
                keys.add(ch.title_key)
            for q in ch.quests:
                if q.title_key: keys.add(q.title_key)
                if q.description_key: keys.add(q.description_key)
        for key in sorted(keys):
            if not key.startswith(("quest.", "task.", "reward.", "quest_link.", "image.", "chapter.", "chapter_group.", "file.", "reward_table.")):
                continue
            r = self.table.rowCount(); self.table.insertRow(r)
            k = QTableWidgetItem(key); k.setFlags(k.flags() & ~Qt.ItemIsEditable)
            p = QTableWidgetItem(self.book.lang_pt.get(key, ""))
            e = QTableWidgetItem(self.book.lang_en.get(key, ""))
            self.table.setItem(r, 0, k); self.table.setItem(r, 1, p); self.table.setItem(r, 2, e)
        self._loading = False
        self._filter()

    def _filter(self):
        q = self.search.text().strip().casefold()
        only_missing = self.missing.isChecked()
        visible = missing = complete = 0
        for r in range(self.table.rowCount()):
            vals = [self.table.item(r, c).text() if self.table.item(r, c) else "" for c in range(3)]
            is_missing = not vals[1].strip() or not vals[2].strip()
            if is_missing: missing += 1
            else: complete += 1
            match = not q or any(q in v.casefold() for v in vals)
            show = match and (not only_missing or is_missing)
            self.table.setRowHidden(r, not show)
            visible += int(show)
        total = self.table.rowCount()
        pct = (complete / total * 100.0) if total else 100.0
        self.summary.setText(f"{visible} exibidas • {missing} com lacunas • {pct:.0f}% completas")

    def _visible_keys(self) -> list[str]:
        keys = []
        for r in range(self.table.rowCount()):
            if self.table.isRowHidden(r):
                continue
            item = self.table.item(r, 0)
            if item and item.text().strip():
                keys.append(item.text().strip())
        return keys

    def _export_report(self):
        if not self.book:
            return QMessageBox.information(self, "Traduções", "Abra um modpack primeiro.")
        default = Path(self.book.root) / "relatorio_traducoes_ftb.csv"
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Exportar relatório de traduções",
            str(default),
            "CSV para Excel/IA (*.csv);;JSON para IA (*.json)",
        )
        if not path:
            return
        p = Path(path)
        if not p.suffix:
            p = p.with_suffix(".json" if "JSON" in selected else ".csv")
        try:
            count = export_translation_report(self.book, p, self._visible_keys())
        except Exception as exc:
            return QMessageBox.critical(self, "Falha ao exportar", str(exc))
        QMessageBox.information(
            self,
            "Relatório exportado",
            f"{count} linha(s) exportada(s).\n\n{p}\n\nO relatório inclui status de tradução e contexto para facilitar envio a uma IA ou tradutor.",
        )

    def _import_report(self):
        if not self.book:
            return QMessageBox.information(self, "Traduções", "Abra um modpack primeiro.")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar relatório de traduções",
            str(self.book.root),
            "Relatórios de tradução (*.csv *.json);;CSV (*.csv);;JSON (*.json)",
        )
        if not path:
            return
        try:
            rows = import_translation_report(Path(path))
        except Exception as exc:
            return QMessageBox.critical(self, "Falha ao importar", str(exc))
        if not rows:
            return QMessageBox.warning(self, "Importação", "Nenhuma tradução válida foi encontrada no arquivo.")
        self.importRequested.emit(rows)

    def _save(self):
        rows = []
        for r in range(self.table.rowCount()):
            key = self.table.item(r, 0).text()
            pt = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            en = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            rows.append((key, pt, en))
        self.saveRequested.emit(rows)
