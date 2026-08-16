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
from ..core.legacy_port import analyze_legacy_snbt_port, port_120_to_121, port_121_to_120
from ..core.port_pipeline import detect_ftb_generation, available_routes, port_route, GEN_120, GEN_121, GEN_2612, GEN_MIXED


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
        tabs.addTab(self._build_universal_port_tab(), "Port Universal")
        tabs.addTab(self._build_convert_tab(), "SNBT ↔ JSON5")
        tabs.addTab(self._build_legacy_port_tab(), "1.20 ↔ 1.21 (Avançado)")
        tabs.addTab(self._build_lang_tab(), "Lang Splitter")
        tabs.setCurrentIndex(max(0, min(int(initial_tab), tabs.count()-1)))

        close = QPushButton("Fechar"); close.clicked.connect(self.accept); root.addWidget(close)
        self._refresh_format()

    def _path_row(self, line: QLineEdit, pick_slot):
        w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(line, 1); b=QPushButton("Procurar…"); b.clicked.connect(pick_slot); lay.addWidget(b)
        return w

    def _build_universal_port_tab(self):
        w=QWidget(); root=QVBoxLayout(w)
        intro=QLabel(
            "Portador por versões do FTB Quests. Escolha a origem e o Alpha detecta a geração, "
            "oferecendo apenas rotas compatíveis: 1.20 → 1.21, 1.20 → 26.1.2 e 1.21 ↔ 26.1.2."
        )
        intro.setWordWrap(True); intro.setObjectName("mutedText"); root.addWidget(intro)

        form=QFormLayout(); form.setSpacing(10)
        self.port_source=QLineEdit(str(self.quest_root or ""))
        form.addRow("Origem", self._path_row(self.port_source, self._pick_port_source))
        self.port_detected=QLabel("—"); self.port_detected.setWordWrap(True)
        form.addRow("Versão detectada", self.port_detected)
        self.port_route=QComboBox(); form.addRow("Rota", self.port_route)
        self.port_locale=QLineEdit("en_us"); self.port_locale.setPlaceholderText("en_us")
        form.addRow("Locale base", self.port_locale)
        default_dst=""
        if self.quest_root:
            default_dst=str(self.quest_root.parent/(self.quest_root.name+"_portado"))
        self.port_destination=QLineEdit(default_dst)
        form.addRow("Destino final", self._path_row(self.port_destination, self._pick_port_destination))
        self.port_remove_lang=QCheckBox("Ao gerar 1.20, remover a pasta lang da cópia")
        self.port_remove_lang.setChecked(True); form.addRow("Backport", self.port_remove_lang)
        root.addLayout(form)

        matrix=QLabel(
            "Rotas: 1.20 → 1.21  •  1.20 → 26.1.2 direto  •  1.20 → 1.21 → 26.1.2 "
            "(mantém intermediário)  •  1.21 → 26.1.2  •  26.1.2 → 1.21.\n"
            "Na rota direta 1.20 → 26.1.2, o Alpha usa uma etapa 1.21 temporária para migrar o lang com segurança."
        )
        matrix.setWordWrap(True); matrix.setObjectName("mutedText"); root.addWidget(matrix)

        row=QHBoxLayout()
        analyze=QPushButton("Analisar origem"); analyze.clicked.connect(self._analyze_universal_port)
        execute=QPushButton("Portar agora"); execute.setObjectName("primaryButton"); execute.clicked.connect(self._execute_universal_port)
        row.addWidget(analyze); row.addWidget(execute); row.addStretch(1); root.addLayout(row)
        self.port_log=QPlainTextEdit(); self.port_log.setReadOnly(True); root.addWidget(self.port_log,1)

        self.port_source.textChanged.connect(self._refresh_universal_port)
        self.port_locale.textChanged.connect(self._refresh_universal_port)
        self.port_route.currentIndexChanged.connect(self._update_universal_destination)
        self._refresh_universal_port()
        return w

    def _pick_port_source(self):
        p=QFileDialog.getExistingDirectory(self,"Selecione o modpack ou config/ftbquests/quests")
        if p:self.port_source.setText(p)

    def _pick_port_destination(self):
        p=QFileDialog.getExistingDirectory(self,"Selecione/crie a pasta de destino final")
        if p:self.port_destination.setText(p)

    def _refresh_universal_port(self):
        if not hasattr(self,"port_source"): return
        raw=self.port_source.text().strip()
        old=self.port_route.currentData() if self.port_route.count() else None
        self.port_route.blockSignals(True); self.port_route.clear()
        if not raw:
            self.port_detected.setText("—"); self.port_route.blockSignals(False); return
        try:
            analysis=detect_ftb_generation(Path(raw),locale=self.port_locale.text().strip() or "en_us")
            labels={
                GEN_120:"FTB Quests 1.20.x — SNBT / textos inline",
                GEN_121:"FTB Quests 1.21.x — SNBT / lang externo",
                GEN_2612:"FTB Quests 26.1.2+ — JSON5 / lang dividido",
                GEN_MIXED:"SNBT misto/parcialmente migrado — escolha a rota explicitamente",
            }
            self.port_detected.setText(labels.get(analysis.generation,"Não identificado"))
            for rid,label in available_routes(analysis.generation):
                self.port_route.addItem(label,rid)
            if old:
                idx=self.port_route.findData(old)
                if idx>=0:self.port_route.setCurrentIndex(idx)
            if not self.port_route.count():
                self.port_route.addItem("Nenhuma rota automática disponível","")
        except Exception as exc:
            self.port_detected.setText(f"Não identificado: {exc}")
            self.port_route.addItem("Nenhuma rota disponível","")
        self.port_route.blockSignals(False)
        self._update_universal_destination()

    def _update_universal_destination(self):
        if not hasattr(self,"port_destination"): return
        raw=self.port_source.text().strip(); route=self.port_route.currentData()
        if not raw or not route:return
        try: src=resolve_quest_root(Path(raw))
        except Exception:return
        suffix={
            "120-121":"_1.21",
            "121-120":"_1.20",
            "121-2612":"_26.1.2",
            "2612-121":"_1.21",
            "120-2612-direct":"_26.1.2",
            "120-121-2612":"_26.1.2",
        }.get(route,"_portado")
        current=self.port_destination.text().strip()
        if not current or current.endswith(("_portado","_1.20","_1.21","_26.1.2")):
            self.port_destination.setText(str(src.parent/f"{src.name}{suffix}"))

    def _analyze_universal_port(self):
        try:
            analysis=detect_ftb_generation(Path(self.port_source.text().strip()),locale=self.port_locale.text().strip() or "en_us")
            routes=available_routes(analysis.generation)
            text=analysis.summary()
            if routes:
                text += "\n\nRotas disponíveis:\n" + "\n".join(f"- {label}" for _,label in routes)
            self.port_log.setPlainText(text)
        except Exception as exc:
            self.port_log.setPlainText(f"ERRO: {exc}"); QMessageBox.critical(self,"Falha na análise",str(exc))

    def _execute_universal_port(self):
        try:
            src=resolve_quest_root(Path(self.port_source.text().strip()))
            dst=Path(self.port_destination.text().strip())
            route=self.port_route.currentData()
            if not route: raise ValueError("Nenhuma rota válida foi selecionada.")
            if not str(dst).strip(): raise ValueError("Escolha a pasta de destino final.")
            if src.resolve()==dst.resolve(): raise ValueError("Origem e destino precisam ser diferentes.")
            if not self._prepare_destination(dst,self): return
            report=port_route(
                src,dst,route=route,locale=self.port_locale.text().strip() or "en_us",
                overwrite=True,remove_lang_on_120_backport=self.port_remove_lang.isChecked(),
            )
            text=report.summary(); self.port_log.setPlainText(text)
            QMessageBox.information(self,"Port concluído",f"Port concluído.\n\n{text}")
        except Exception as exc:
            self.port_log.setPlainText(f"ERRO: {exc}"); QMessageBox.critical(self,"Falha no port",str(exc))

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

    def _build_legacy_port_tab(self):
        w=QWidget(); root=QVBoxLayout(w)
        intro=QLabel(
            "Porta Quest Books SNBT entre a linha FTB Quests 1.20.x (texto dentro dos capítulos/quests) "
            "e 1.21.x (texto em lang/<locale>.snbt). A origem nunca é alterada."
        )
        intro.setWordWrap(True); intro.setObjectName("mutedText"); root.addWidget(intro)

        form=QFormLayout(); form.setSpacing(10)
        self.legacy_source=QLineEdit(str(self.quest_root or ""))
        form.addRow("Origem", self._path_row(self.legacy_source, self._pick_legacy_source))
        self.legacy_detected=QLabel("—"); self.legacy_detected.setWordWrap(True)
        form.addRow("Detectado", self.legacy_detected)
        self.legacy_direction=QComboBox()
        self.legacy_direction.addItem("Detectar automaticamente", "auto")
        self.legacy_direction.addItem("FTB 1.20.x → 1.21.x — mover textos para lang", "120-to-121")
        self.legacy_direction.addItem("FTB 1.21.x → 1.20.x — embutir lang no SNBT", "121-to-120")
        form.addRow("Direção", self.legacy_direction)
        self.legacy_locale=QLineEdit("en_us"); self.legacy_locale.setPlaceholderText("en_us")
        form.addRow("Locale", self.legacy_locale)
        legacy_dst=""
        if self.quest_root:
            legacy_dst=str(self.quest_root.parent/(self.quest_root.name+"_portado"))
        self.legacy_destination=QLineEdit(legacy_dst)
        form.addRow("Destino", self._path_row(self.legacy_destination, self._pick_legacy_destination))
        self.legacy_remove_lang=QCheckBox("No backport 1.21 → 1.20, remover a pasta lang da cópia")
        self.legacy_remove_lang.setChecked(True)
        form.addRow("Backport", self.legacy_remove_lang)
        root.addLayout(form)

        note=QLabel(
            "O Alpha migra o sistema de textos e preserva os demais campos. ItemStacks/NBT legado e recursos "
            "específicos de versão são sinalizados para revisão; teste sempre a cópia no Minecraft de destino."
        )
        note.setWordWrap(True); note.setObjectName("mutedText"); root.addWidget(note)
        row=QHBoxLayout()
        analyze=QPushButton("Analisar origem"); analyze.clicked.connect(self._analyze_legacy_port)
        port=QPushButton("Portar agora"); port.setObjectName("primaryButton"); port.clicked.connect(self._port_legacy)
        row.addWidget(analyze); row.addWidget(port); row.addStretch(1); root.addLayout(row)
        self.legacy_log=QPlainTextEdit(); self.legacy_log.setReadOnly(True); root.addWidget(self.legacy_log,1)
        self.legacy_source.textChanged.connect(self._legacy_source_changed)
        self.legacy_direction.currentIndexChanged.connect(self._legacy_update_hint)
        self.legacy_locale.textChanged.connect(self._legacy_source_changed)
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

    def _pick_legacy_source(self):
        p=QFileDialog.getExistingDirectory(self,"Selecione o modpack ou config/ftbquests/quests SNBT")
        if p:self.legacy_source.setText(p)

    def _pick_legacy_destination(self):
        p=QFileDialog.getExistingDirectory(self,"Selecione/crie a pasta de destino do port")
        if p:self.legacy_destination.setText(p)

    def _legacy_source_changed(self):
        if not hasattr(self,"legacy_source"): return
        path=self.legacy_source.text().strip()
        if not path:
            self.legacy_detected.setText("—")
            return
        try:
            analysis=analyze_legacy_snbt_port(Path(path),locale=self.legacy_locale.text().strip() or "en_us")
            labels={
                "120-to-121":"FTB 1.20.x provável — texto inline encontrado",
                "121-to-120":"FTB 1.21.x provável — traduções externas encontradas",
                "mixed":"Misto/parcialmente migrado — inline + lang",
                "unknown":"SNBT reconhecido, geração não conclusiva",
            }
            self.legacy_detected.setText(labels.get(analysis.direction,analysis.direction))
        except Exception as exc:
            self.legacy_detected.setText(f"Não identificado: {exc}")
        self._legacy_update_hint()

    def _legacy_update_hint(self):
        if not hasattr(self,"legacy_destination"): return
        src_text=self.legacy_source.text().strip()
        if not src_text:return
        try: src=resolve_quest_root(Path(src_text))
        except Exception: return
        mode=self.legacy_direction.currentData()
        suffix="_portado"
        if mode=="120-to-121": suffix="_1.21"
        elif mode=="121-to-120": suffix="_1.20"
        current=self.legacy_destination.text().strip()
        if not current or current.endswith(("_portado","_1.20","_1.21")):
            self.legacy_destination.setText(str(src.parent/f"{src.name}{suffix}"))

    def _analyze_legacy_port(self):
        try:
            root=resolve_quest_root(Path(self.legacy_source.text().strip()))
            analysis=analyze_legacy_snbt_port(root,locale=self.legacy_locale.text().strip() or "en_us")
            self.legacy_log.setPlainText(analysis.summary())
            self._legacy_source_changed()
        except Exception as exc:
            self.legacy_log.setPlainText(f"ERRO: {exc}")
            QMessageBox.critical(self,"Falha na análise",str(exc))

    def _port_legacy(self):
        try:
            src=resolve_quest_root(Path(self.legacy_source.text().strip()))
            dst=Path(self.legacy_destination.text().strip())
            if not src.exists(): raise FileNotFoundError(src)
            if not str(dst).strip(): raise ValueError("Escolha uma pasta de destino.")
            if src.resolve()==dst.resolve(): raise ValueError("Origem e destino precisam ser diferentes.")
            locale=self.legacy_locale.text().strip() or "en_us"
            analysis=analyze_legacy_snbt_port(src,locale=locale)
            mode=self.legacy_direction.currentData()
            if mode=="auto":
                if analysis.direction in ("120-to-121","121-to-120"):
                    mode=analysis.direction
                elif analysis.direction=="mixed":
                    raise ValueError("O projeto contém texto inline e lang externo. Escolha explicitamente a direção para evitar uma migração ambígua.")
                else:
                    raise ValueError("Não foi possível detectar automaticamente a direção. Escolha 1.20 → 1.21 ou 1.21 → 1.20.")
            if not self._prepare_destination(dst,self): return
            # _prepare_destination above empties the folder; the core owns the
            # actual copy and uses overwrite=True for an atomic, deterministic port.
            if mode=="120-to-121":
                report=port_120_to_121(src,dst,locale=locale,overwrite=True)
            else:
                report=port_121_to_120(src,dst,locale=locale,overwrite=True,remove_lang=self.legacy_remove_lang.isChecked())
            text=report.summary()+f"\n\nDestino:\n{dst}"
            self.legacy_log.setPlainText(text)
            QMessageBox.information(self,"Port concluído",text)
        except Exception as exc:
            self.legacy_log.setPlainText(f"ERRO: {exc}")
            QMessageBox.critical(self,"Falha no port",str(exc))

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

