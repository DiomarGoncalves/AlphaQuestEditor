from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from ..core.backup import backup_questbook
from ..core.format_conversion import (
    convert_json5_to_snbt, convert_snbt_to_json5, detect_quest_format,
    fill_missing_snbt_translations, merge_snbt_languages, purge_merged_snbt_languages,
    resolve_quest_root, split_snbt_languages,
)


class ConverterDialog(QDialog):
    projectChanged = Signal()

    def __init__(self, quest_root: Path | None = None, parent=None, initial_tab: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Conversor / Lang Splitter")
        self.resize(780, 650)
        self.quest_root = resolve_quest_root(quest_root) if quest_root else None

        root = QVBoxLayout(self)
        intro = QLabel(
            "Ferramentas de portabilidade do Quest Book. A conversão sempre pode ser feita em uma pasta nova; "
            "Split/Merge de idiomas trabalha no projeto atual e cria backup antes de alterar arquivos."
        )
        intro.setWordWrap(True); intro.setObjectName("mutedText"); root.addWidget(intro)
        tabs = QTabWidget(); self.tabs=tabs; root.addWidget(tabs, 1)
        tabs.addTab(self._build_convert_tab(), "SNBT ↔ JSON5")
        tabs.addTab(self._build_lang_tab(), "Lang Splitter")
        tabs.setCurrentIndex(1 if int(initial_tab)==1 else 0)

        close = QPushButton("Fechar"); close.clicked.connect(self.accept); root.addWidget(close)
        self._refresh_format()

    def _path_row(self, line: QLineEdit, pick_slot):
        w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(line, 1); b=QPushButton("Procurar…"); b.clicked.connect(pick_slot); lay.addWidget(b)
        return w

    def _build_convert_tab(self):
        w=QWidget(); root=QVBoxLayout(w)
        form=QFormLayout(); form.setSpacing(10)
        self.source=QLineEdit(str(self.quest_root or "")); form.addRow("Origem", self._path_row(self.source,self._pick_source))
        self.source_format=QLabel("—"); form.addRow("Formato detectado",self.source_format)
        self.direction=QComboBox(); self.direction.addItem("Detectar automaticamente e converter para o outro formato","auto"); self.direction.addItem("SNBT 1.21.1 → JSON5 26.1.2","snbt-json5"); self.direction.addItem("JSON5 26.1.2 → SNBT 1.21.1","json5-snbt"); form.addRow("Conversão",self.direction)
        default_dst=""
        if self.quest_root:
            default_dst=str(self.quest_root.parent/(self.quest_root.name+"_convertido"))
        self.destination=QLineEdit(default_dst); form.addRow("Destino",self._path_row(self.destination,self._pick_destination))
        self.split_on_reverse=QCheckBox("Ao gerar SNBT, dividir idiomas no layout do Quests Lang Splitter")
        self.split_on_reverse.setChecked(False); form.addRow("Idiomas",self.split_on_reverse)
        root.addLayout(form)
        note=QLabel("Dica: use uma pasta de destino vazia. O projeto original não é substituído pela conversão.")
        note.setObjectName("mutedText"); note.setWordWrap(True); root.addWidget(note)
        row=QHBoxLayout(); self.convert_btn=QPushButton("Converter agora"); self.convert_btn.setObjectName("primaryButton"); self.convert_btn.clicked.connect(self._convert); row.addWidget(self.convert_btn); row.addStretch(1); root.addLayout(row)
        self.convert_log=QPlainTextEdit(); self.convert_log.setReadOnly(True); root.addWidget(self.convert_log,1)
        self.source.textChanged.connect(self._refresh_format); self.direction.currentIndexChanged.connect(self._update_destination_hint)
        return w

    def _build_lang_tab(self):
        w=QWidget(); root=QVBoxLayout(w)
        self.lang_project=QLineEdit(str(self.quest_root or "")); root.addWidget(QLabel("Quest Book SNBT (1.21.1)")); root.addWidget(self._path_row(self.lang_project,self._pick_lang_project))
        self.locales=QLineEdit(); self.locales.setPlaceholderText("Vazio = todos os idiomas; ou pt_br,en_us")
        root.addWidget(QLabel("Locales")); root.addWidget(self.locales)
        self.keep_flat=QCheckBox("Manter também o arquivo flat lang/<locale>.snbt")
        self.keep_flat.setChecked(True); root.addWidget(self.keep_flat)
        info=QLabel(
            "Dividir cria lang/<locale>/chapters/<capitulo>.snbt e os arquivos chapter.snbt, chapter_group.snbt, file.snbt e reward_table.snbt. "
            "Mesclar faz o caminho contrário e recria lang/<locale>.snbt."
        ); info.setWordWrap(True); info.setObjectName("mutedText"); root.addWidget(info)
        row=QHBoxLayout(); split=QPushButton("Dividir idiomas"); split.clicked.connect(self._split); merge=QPushButton("Mesclar idiomas"); merge.clicked.connect(self._merge); row.addWidget(split); row.addWidget(merge); row.addStretch(1); root.addLayout(row)

        root.addWidget(QLabel("Preencher traduções ausentes"))
        fill_form=QFormLayout(); fill_form.setSpacing(8)
        self.fallback_locale=QLineEdit("en_us"); self.target_locale=QLineEdit("pt_br")
        self.fallback_locale.setPlaceholderText("en_us"); self.target_locale.setPlaceholderText("pt_br")
        fill_form.addRow("Usar textos de",self.fallback_locale); fill_form.addRow("Preencher locale",self.target_locale); root.addLayout(fill_form)
        fill_note=QLabel("Copia apenas chaves ausentes/vazias do locale de origem e depois divide o locale de destino. Textos já traduzidos são preservados.")
        fill_note.setWordWrap(True); fill_note.setObjectName("mutedText"); root.addWidget(fill_note)
        util_row=QHBoxLayout(); fill=QPushButton("Preencher ausentes + dividir"); fill.clicked.connect(self._fill_missing); purge=QPushButton("Limpar *.snbt_merged"); purge.clicked.connect(self._purge_merged); util_row.addWidget(fill); util_row.addWidget(purge); util_row.addStretch(1); root.addLayout(util_row)

        self.lang_log=QPlainTextEdit(); self.lang_log.setReadOnly(True); root.addWidget(self.lang_log,1)
        return w

    def _pick_source(self):
        p=QFileDialog.getExistingDirectory(self,"Selecione a pasta do modpack ou config/ftbquests/quests")
        if p:self.source.setText(p)

    def _pick_destination(self):
        p=QFileDialog.getExistingDirectory(self,"Selecione/crie a pasta de destino")
        if p:self.destination.setText(p)

    def _pick_lang_project(self):
        p=QFileDialog.getExistingDirectory(self,"Selecione a pasta do modpack ou config/ftbquests/quests")
        if p:self.lang_project.setText(p)

    def _refresh_format(self):
        path=self.source.text().strip() if hasattr(self,"source") else ""
        if not path:
            if hasattr(self,"source_format"):self.source_format.setText("—")
            return
        fmt=detect_quest_format(Path(path)); label={"snbt":"SNBT (FTB Quests 2101.x / 1.21.1)","json5":"JSON5 (FTB Quests 26.1.2+)","mixed":"Misto (SNBT + JSON5)","unknown":"Não identificado"}.get(fmt,fmt)
        self.source_format.setText(label)
        self._update_destination_hint()

    def _update_destination_hint(self):
        if not hasattr(self,"destination"):return
        src_text=self.source.text().strip()
        if not src_text:return
        src=resolve_quest_root(Path(src_text)); mode=self.direction.currentData(); fmt=detect_quest_format(src)
        target_fmt="json5" if mode=="snbt-json5" or (mode=="auto" and fmt=="snbt") else "snbt" if mode=="json5-snbt" or (mode=="auto" and fmt=="json5") else "convertido"
        current=self.destination.text().strip()
        if not current or current.endswith(("_convertido","_json5","_snbt")):
            self.destination.setText(str(src.parent/f"{src.name}_{target_fmt}"))

    @staticmethod
    def _prepare_destination(dst: Path, parent) -> bool:
        if not dst.exists() or not any(dst.iterdir()):
            return True
        ans=QMessageBox.warning(parent,"Destino não vazio",f"A pasta de destino já contém arquivos:\n{dst}\n\nApagar o conteúdo dessa pasta antes da conversão?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if ans!=QMessageBox.Yes:return False
        shutil.rmtree(dst); dst.mkdir(parents=True,exist_ok=True); return True

    def _convert(self):
        try:
            src=resolve_quest_root(Path(self.source.text().strip())); dst=Path(self.destination.text().strip())
            fmt=detect_quest_format(src); mode=self.direction.currentData()
            if mode=="auto":
                if fmt=="snbt":mode="snbt-json5"
                elif fmt=="json5":mode="json5-snbt"
                else:raise ValueError("Não foi possível escolher automaticamente: a origem está mista ou não foi reconhecida.")
            if not src.exists():raise FileNotFoundError(src)
            if src.resolve()==dst.resolve():raise ValueError("Escolha uma pasta de destino diferente da origem.")
            if not self._prepare_destination(dst,self):return
            if mode=="snbt-json5":
                if fmt not in ("snbt","mixed"):raise ValueError("A origem não contém um Quest Book SNBT.")
                report=convert_snbt_to_json5(src,dst,overwrite=True)
            else:
                if fmt not in ("json5","mixed"):raise ValueError("A origem não contém um Quest Book JSON5.")
                report=convert_json5_to_snbt(src,dst,overwrite=True,split_lang=self.split_on_reverse.isChecked())
            self.convert_log.setPlainText(report.summary()+f"\n\nDestino:\n{dst}")
            QMessageBox.information(self,"Conversão concluída",f"Conversão concluída.\n\n{report.summary()}\n\nDestino: {dst}")
        except Exception as exc:
            self.convert_log.setPlainText(f"ERRO: {exc}"); QMessageBox.critical(self,"Falha na conversão",str(exc))

    def _selected_locales(self):
        raw=self.locales.text().replace(";",",")
        values=[x.strip() for x in raw.split(",") if x.strip()]
        return values or None

    def _split(self):
        try:
            root=resolve_quest_root(Path(self.lang_project.text().strip()))
            if detect_quest_format(root) not in ("snbt","mixed"):raise ValueError("Lang Splitter é destinado ao Quest Book SNBT/1.21.1.")
            backup=backup_questbook(root)
            report=split_snbt_languages(root,locales=self._selected_locales(),keep_flat=self.keep_flat.isChecked())
            text=report.summary()+f"\n\nBackup: {backup or 'não criado'}"; self.lang_log.setPlainText(text); self.projectChanged.emit(); QMessageBox.information(self,"Idiomas divididos",text)
        except Exception as exc:self.lang_log.setPlainText(f"ERRO: {exc}"); QMessageBox.critical(self,"Falha",str(exc))

    def _merge(self):
        try:
            root=resolve_quest_root(Path(self.lang_project.text().strip()))
            if detect_quest_format(root) not in ("snbt","mixed"):raise ValueError("Merge do Lang Splitter é destinado ao Quest Book SNBT/1.21.1.")
            backup=backup_questbook(root)
            report=merge_snbt_languages(root,locales=self._selected_locales())
            text=report.summary()+f"\n\nBackup: {backup or 'não criado'}"; self.lang_log.setPlainText(text); self.projectChanged.emit(); QMessageBox.information(self,"Idiomas mesclados",text)
        except Exception as exc:self.lang_log.setPlainText(f"ERRO: {exc}"); QMessageBox.critical(self,"Falha",str(exc))
    def _fill_missing(self):
        try:
            root=resolve_quest_root(Path(self.lang_project.text().strip()))
            if detect_quest_format(root) not in ("snbt","mixed"):raise ValueError("Preenchimento do Lang Splitter é destinado ao Quest Book SNBT/1.21.1.")
            target=self.target_locale.text().strip(); fallback=self.fallback_locale.text().strip() or "en_us"
            backup=backup_questbook(root)
            report=fill_missing_snbt_translations(root,target_locale=target,source_locale=fallback,keep_flat=self.keep_flat.isChecked())
            text=report.summary()+f"\n\nBackup: {backup or 'não criado'}"; self.lang_log.setPlainText(text); self.projectChanged.emit(); QMessageBox.information(self,"Traduções preenchidas",text)
        except Exception as exc:self.lang_log.setPlainText(f"ERRO: {exc}"); QMessageBox.critical(self,"Falha",str(exc))

    def _purge_merged(self):
        try:
            root=resolve_quest_root(Path(self.lang_project.text().strip()))
            if detect_quest_format(root) not in ("snbt","mixed"):raise ValueError("Limpeza .snbt_merged é destinada ao Quest Book SNBT/1.21.1.")
            report=purge_merged_snbt_languages(root,locales=self._selected_locales())
            text=report.summary(); self.lang_log.setPlainText(text); self.projectChanged.emit(); QMessageBox.information(self,"Arquivos limpos",text)
        except Exception as exc:self.lang_log.setPlainText(f"ERRO: {exc}"); QMessageBox.critical(self,"Falha",str(exc))

