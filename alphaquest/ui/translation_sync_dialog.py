from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.translation_sync import (
    analyze_translation_file, available_locales, guess_locale_from_path,
    validate_locale_files,
)


class TranslationSyncDialog(QDialog):
    """Crowdin-like import preview + project QA for translation files."""

    applyRequested = Signal(str, object)  # locale, list[{key,value}]

    def __init__(self, book, parent=None):
        super().__init__(parent)
        self.book = book
        self.analysis = None
        self.setWindowTitle("Central de Tradução — Importar e validar")
        self.resize(1180, 760)
        self.setModal(False)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Importe um arquivo de idioma atualizado sem copiar manualmente para a pasta do modpack. "
            "O Alpha compara as chaves, executa QA e grava cada tradução no arquivo correto do projeto."
        )
        intro.setWordWrap(True)
        intro.setObjectName("mutedText")
        root.addWidget(intro)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_import_tab(), "Importar atualização")
        self.tabs.addTab(self._build_qa_tab(), "QA do projeto")
        root.addWidget(self.tabs, 1)

        close_bar = QHBoxLayout(); close_bar.addStretch(1)
        close_btn = QPushButton("Fechar"); close_btn.clicked.connect(self.close); close_bar.addWidget(close_btn)
        root.addLayout(close_bar)
        self._load_locales()

    def _load_locales(self):
        locales = available_locales(self.book)
        for combo in (self.target_locale, self.source_locale, self.qa_locale):
            combo.clear(); combo.addItems(locales); combo.setEditable(True)
        self.target_locale.setCurrentText("pt_br")
        self.source_locale.setCurrentText("en_us")
        self.qa_locale.setCurrentText("pt_br")

    # ---------------- import ----------------
    def _build_import_tab(self):
        page = QWidget(); root = QVBoxLayout(page)
        form = QFormLayout()
        file_row = QHBoxLayout()
        self.file_path = QLineEdit(); self.file_path.setReadOnly(True); self.file_path.setPlaceholderText("Selecione pt_br.snbt, en_us.snbt ou um arquivo JSON5 de idioma...")
        browse = QPushButton("Escolher arquivo..."); browse.clicked.connect(self._browse)
        file_row.addWidget(self.file_path, 1); file_row.addWidget(browse)
        file_wrap = QWidget(); file_wrap.setLayout(file_row)
        form.addRow("Arquivo atualizado", file_wrap)

        loc_row = QHBoxLayout()
        self.target_locale = QComboBox(); self.source_locale = QComboBox()
        loc_row.addWidget(QLabel("Destino")); loc_row.addWidget(self.target_locale)
        loc_row.addSpacing(16); loc_row.addWidget(QLabel("Origem para QA")); loc_row.addWidget(self.source_locale)
        loc_wrap = QWidget(); loc_wrap.setLayout(loc_row)
        form.addRow("Idiomas", loc_wrap)
        root.addLayout(form)

        bar = QHBoxLayout()
        self.analyze_btn = QPushButton("Analisar arquivo"); self.analyze_btn.setObjectName("primaryButton"); self.analyze_btn.clicked.connect(self._analyze)
        self.import_search = QLineEdit(); self.import_search.setPlaceholderText("Filtrar chave, status, texto ou problema..."); self.import_search.textChanged.connect(self._filter_import)
        self.only_changes = QCheckBox("Ocultar iguais"); self.only_changes.setChecked(True); self.only_changes.toggled.connect(self._filter_import)
        bar.addWidget(self.analyze_btn); bar.addWidget(self.import_search, 1); bar.addWidget(self.only_changes)
        root.addLayout(bar)

        self.import_summary = QLabel("Nenhum arquivo analisado."); self.import_summary.setObjectName("liveStatus"); self.import_summary.setWordWrap(True); root.addWidget(self.import_summary)

        self.import_table = QTableWidget(0, 7)
        self.import_table.setHorizontalHeaderLabels(["Aplicar", "Status", "Linha", "Chave", "Atual", "Importado", "QA"])
        hdr = self.import_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents); hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents); hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents); hdr.setSectionResizeMode(4, QHeaderView.Stretch); hdr.setSectionResizeMode(5, QHeaderView.Stretch); hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        self.import_table.setAlternatingRowColors(True); self.import_table.setWordWrap(True); self.import_table.verticalHeader().setDefaultSectionSize(54)
        root.addWidget(self.import_table, 1)

        bottom = QHBoxLayout()
        self.select_safe = QPushButton("Marcar alterações seguras"); self.select_safe.clicked.connect(self._mark_safe)
        self.unselect_all = QPushButton("Desmarcar tudo"); self.unselect_all.clicked.connect(lambda: self._mark_all(False))
        self.apply_btn = QPushButton("Aplicar selecionadas"); self.apply_btn.setObjectName("primaryButton"); self.apply_btn.clicked.connect(self._apply); self.apply_btn.setEnabled(False)
        bottom.addWidget(self.select_safe); bottom.addWidget(self.unselect_all); bottom.addStretch(1); bottom.addWidget(self.apply_btn)
        root.addLayout(bottom)
        return page

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar arquivo de tradução", str(self.book.quest_root / "lang"),
            "Arquivos de idioma (*.snbt *.json5 *.json);;SNBT (*.snbt);;JSON5 (*.json5 *.json);;Todos (*.*)",
        )
        if not path:
            return
        self.file_path.setText(path)
        guessed = guess_locale_from_path(path)
        if guessed:
            self.target_locale.setCurrentText(guessed)
            if guessed != "en_us": self.source_locale.setCurrentText("en_us")
        self._analyze()

    def _analyze(self):
        path = Path(self.file_path.text().strip())
        if not path.exists():
            return QMessageBox.information(self, "Importar tradução", "Escolha um arquivo de idioma primeiro.")
        try:
            self.analysis = analyze_translation_file(self.book, path, self.target_locale.currentText(), self.source_locale.currentText())
        except Exception as exc:
            return QMessageBox.critical(self, "Falha ao analisar", str(exc))
        self._populate_import()

    def _populate_import(self):
        self.import_table.setRowCount(0)
        a = self.analysis
        if not a:
            return
        # Global syntax/file issues are shown as pseudo rows so exact line remains visible.
        for issue in a.issues:
            r = self.import_table.rowCount(); self.import_table.insertRow(r)
            apply_item = QTableWidgetItem(); apply_item.setFlags(Qt.ItemIsEnabled)
            self.import_table.setItem(r, 0, apply_item)
            self.import_table.setItem(r, 1, QTableWidgetItem(issue.severity.upper()))
            self.import_table.setItem(r, 2, QTableWidgetItem(str(issue.line or "")))
            self.import_table.setItem(r, 3, QTableWidgetItem(issue.key or "— arquivo —"))
            self.import_table.setItem(r, 4, QTableWidgetItem("")); self.import_table.setItem(r, 5, QTableWidgetItem(""))
            self.import_table.setItem(r, 6, QTableWidgetItem(issue.message))
            self.import_table.item(r, 0).setData(Qt.UserRole, None)
        for row in a.rows:
            r = self.import_table.rowCount(); self.import_table.insertRow(r)
            check = QTableWidgetItem(); check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            safe = row.status in ("ALTERADA", "NOVA") and not row.has_error
            check.setCheckState(Qt.Checked if safe else Qt.Unchecked); check.setData(Qt.UserRole, row)
            self.import_table.setItem(r, 0, check)
            self.import_table.setItem(r, 1, QTableWidgetItem(row.status))
            self.import_table.setItem(r, 2, QTableWidgetItem(str(row.line or "")))
            self.import_table.setItem(r, 3, QTableWidgetItem(row.key))
            self.import_table.setItem(r, 4, QTableWidgetItem(row.current))
            self.import_table.setItem(r, 5, QTableWidgetItem(row.imported))
            self.import_table.setItem(r, 6, QTableWidgetItem(row.qa_text or "OK"))
        counts = {name: sum(r.status == name for r in a.rows) for name in ("ALTERADA", "NOVA", "IGUAL", "CHAVE_DESCONHECIDA")}
        self.import_summary.setText(
            f"{a.path.name} • {a.source_format.upper()} • destino {a.target_locale} • "
            f"{counts['ALTERADA']} alteradas • {counts['NOVA']} novas • {counts['IGUAL']} iguais • "
            f"{counts['CHAVE_DESCONHECIDA']} chaves desconhecidas • {a.errors} erro(s) • {a.warnings} aviso(s).\n"
            "Erros de sintaxe e chaves suspeitas mostram a linha exata. Chaves desconhecidas não são marcadas automaticamente."
        )
        self.apply_btn.setEnabled(bool(a.rows) and not any(i.severity == "error" and i.code == "SYNTAX" for i in a.issues))
        self._filter_import()

    def _filter_import(self):
        q = self.import_search.text().strip().casefold()
        hide_equal = self.only_changes.isChecked()
        for r in range(self.import_table.rowCount()):
            status = self.import_table.item(r, 1).text() if self.import_table.item(r, 1) else ""
            vals = [self.import_table.item(r, c).text() if self.import_table.item(r, c) else "" for c in range(1, 7)]
            show = (not hide_equal or status != "IGUAL") and (not q or any(q in x.casefold() for x in vals))
            self.import_table.setRowHidden(r, not show)

    def _mark_all(self, checked: bool):
        for r in range(self.import_table.rowCount()):
            item = self.import_table.item(r, 0)
            if item and item.data(Qt.UserRole) is not None:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _mark_safe(self):
        for r in range(self.import_table.rowCount()):
            item = self.import_table.item(r, 0)
            row = item.data(Qt.UserRole) if item else None
            if row is not None:
                item.setCheckState(Qt.Checked if row.status in ("ALTERADA", "NOVA") and not row.has_error else Qt.Unchecked)

    def _apply(self):
        if not self.analysis:
            return
        chosen = []
        unknown = []
        for r in range(self.import_table.rowCount()):
            item = self.import_table.item(r, 0)
            row = item.data(Qt.UserRole) if item else None
            if row is None or item.checkState() != Qt.Checked:
                continue
            if row.status == "IGUAL":
                continue
            if row.has_error and row.status != "CHAVE_DESCONHECIDA":
                continue
            if row.status == "CHAVE_DESCONHECIDA":
                unknown.append(row.key)
            chosen.append({"key": row.key, "value": row.imported, "status": row.status})
        if not chosen:
            return QMessageBox.information(self, "Importar tradução", "Nenhuma alteração foi marcada para aplicar.")
        if unknown:
            preview = "\n".join(f"• {k}" for k in unknown[:8])
            if len(unknown) > 8: preview += f"\n• ... e mais {len(unknown)-8}"
            ans = QMessageBox.warning(
                self, "Chaves desconhecidas",
                "Você marcou chaves que não existem no Quest Book atual. Isso pode ser um erro de ID/dígito.\n\n" + preview + "\n\nAplicar mesmo assim?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return
        self.applyRequested.emit(self.analysis.target_locale, chosen)

    # ---------------- QA current project ----------------
    def _build_qa_tab(self):
        page = QWidget(); root = QVBoxLayout(page)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Locale")); self.qa_locale = QComboBox(); bar.addWidget(self.qa_locale)
        validate = QPushButton("Validar arquivos atuais"); validate.setObjectName("primaryButton"); validate.clicked.connect(self._validate_project); bar.addWidget(validate)
        self.qa_search = QLineEdit(); self.qa_search.setPlaceholderText("Filtrar arquivo, chave ou mensagem..."); self.qa_search.textChanged.connect(self._filter_qa); bar.addWidget(self.qa_search, 1)
        root.addLayout(bar)
        self.qa_summary = QLabel("Valide o locale para localizar strings quebradas, chaves suspeitas, placeholders, números e quebras de linha.")
        self.qa_summary.setObjectName("liveStatus"); self.qa_summary.setWordWrap(True); root.addWidget(self.qa_summary)
        self.qa_table = QTableWidget(0, 5)
        self.qa_table.setHorizontalHeaderLabels(["Nível", "Arquivo", "Linha", "Chave", "Problema"])
        hdr = self.qa_table.horizontalHeader(); hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents); hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents); hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents); hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents); hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        self.qa_table.setAlternatingRowColors(True); self.qa_table.setWordWrap(True); self.qa_table.verticalHeader().setDefaultSectionSize(48)
        root.addWidget(self.qa_table, 1)
        return page

    def _validate_project(self):
        try:
            issues = validate_locale_files(self.book, self.qa_locale.currentText())
        except Exception as exc:
            return QMessageBox.critical(self, "QA de tradução", str(exc))
        self.qa_table.setRowCount(0)
        for issue in issues:
            r = self.qa_table.rowCount(); self.qa_table.insertRow(r)
            self.qa_table.setItem(r, 0, QTableWidgetItem(issue.severity.upper()))
            try: rel = str(Path(issue.file).relative_to(self.book.quest_root)) if issue.file else ""
            except Exception: rel = issue.file
            self.qa_table.setItem(r, 1, QTableWidgetItem(rel))
            self.qa_table.setItem(r, 2, QTableWidgetItem(str(issue.line or "")))
            self.qa_table.setItem(r, 3, QTableWidgetItem(issue.key))
            self.qa_table.setItem(r, 4, QTableWidgetItem(issue.message))
        errors = sum(i.severity == "error" for i in issues); warnings = sum(i.severity == "warning" for i in issues); infos = len(issues) - errors - warnings
        self.qa_summary.setText(f"{self.qa_locale.currentText()} • {errors} erro(s) • {warnings} aviso(s) • {infos} informação(ões) • {len(issues)} problema(s) encontrados.")
        if not issues:
            self.qa_summary.setText(f"{self.qa_locale.currentText()} • QA concluído: nenhum problema encontrado.")
        self._filter_qa()

    def _filter_qa(self):
        q = self.qa_search.text().strip().casefold()
        for r in range(self.qa_table.rowCount()):
            vals = [self.qa_table.item(r, c).text() if self.qa_table.item(r, c) else "" for c in range(self.qa_table.columnCount())]
            self.qa_table.setRowHidden(r, bool(q) and not any(q in v.casefold() for v in vals))
