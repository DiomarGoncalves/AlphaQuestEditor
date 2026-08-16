from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer, QSettings, QThread, QUrl
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QProgressDialog, QPushButton, QSplitter, QTabWidget, QToolBar, QDoubleSpinBox, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
    QToolButton, QSizePolicy, QApplication,
)

from ..core.backup import backup_questbook
from ..core.mod_index import ModIndex
from ..core.history import QuestHistory
from ..core.diagnostics import diagnostic_text, logs_dir
from ..core.models import ChapterGroupInfo, ChapterInfo
from ..core.questbook import QuestBook
from ..core.validator import validate
from .canvas import QuestCanvas
from .batch_dependencies import BatchDependenciesDialog
from .dependency_mapper import DependencyMapperDialog
from .item_browser import ItemBrowser
from .new_quest import NewQuestDialog
from .problems import ProblemsPanel
from .properties import QuestProperties
from .structure_dialogs import ChapterDialog, GroupDialog
from .translations import TranslationEditor
from .translation_sync_dialog import TranslationSyncDialog
from .converter_dialog import ConverterDialog
from .theme_dialog import ThemeDialog
from .asset_library import AssetLibraryDialog
from .scan_worker import ModScanWorker
from ..version import APP_VERSION
from ..theme import apply_theme, load_theme, save_theme


ROLE_KIND = Qt.UserRole
ROLE_OBJECT = Qt.UserRole + 1


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(f"Alpha Quest Editor — {APP_VERSION}"); self.resize(1600,920); self.setMinimumSize(900,600)
        self.book: QuestBook|None=None; self.mods=ModIndex(); self.history=QuestHistory(); self.current_chapter:ChapterInfo|None=None; self.current_quest=None
        self.settings=QSettings("Alpha Devs","Alpha Quest Editor"); self.contextual_layout=True; self.dependency_mapper=None; self.translation_sync=None; self.asset_library=None; self.auto_show_inspector=True; self.auto_compact=True; self._focus_mode_state=None; self._preferred_visibility={"left":True,"right":True,"problems":True}
        self._ignore_external_until=0.0; self._select_after_reload=""; self._scan_thread=None; self._scan_worker=None; self._scan_dialog=None; self._scan_root=None
        self.file_watcher=QFileSystemWatcher(self); self.file_watcher.fileChanged.connect(self._external_change); self.file_watcher.directoryChanged.connect(self._external_change)
        self.reload_timer=QTimer(self); self.reload_timer.setSingleShot(True); self.reload_timer.timeout.connect(self.reload_questbook); self._build_ui()

    def _action(self,text,shortcut,slot,toolbar=None):
        a=QAction(text,self)
        if shortcut:a.setShortcut(QKeySequence(shortcut)); a.setShortcutContext(Qt.ApplicationShortcut)
        a.triggered.connect(slot); self.addAction(a)
        if toolbar: toolbar.addAction(a)
        return a

    def _build_ui(self):
        tb=QToolBar("Principal"); tb.setObjectName("mainToolbar"); tb.setMovable(False); tb.setFloatable(False); self.addToolBar(tb); self.main_tb=tb
        # 0.9.1: barra principal compacta. Ações frequentes ficam em uma única linha;
        # instruções longas saem da toolbar e passam para tooltips/status bar.
        self._action("Abrir",QKeySequence.Open,self.choose_modpack,tb).setToolTip("Abrir modpack (Ctrl+O)")
        self._action("↻",QKeySequence.Refresh,self.reload_questbook,tb).setToolTip("Recarregar Quest Book")
        self.index_action=self._action("Indexar",None,lambda:self.scan_mods(force=True),tb); self.index_action.setToolTip("Forçar nova leitura dos itens do Minecraft e dos mods")

        # Edição de quest: as funções mais usadas ficam expostas na navbar, como no editor in-game.
        tb.addSeparator()
        self.new_quest_action=self._action("＋Quest","Ctrl+N",self._new_quest_center,tb); self.new_quest_action.setToolTip("Nova Quest (Ctrl+N)")
        self.properties_action=self._action("Prop.","Ctrl+E",self._show_current_properties,tb); self.properties_action.setToolTip("Abrir propriedades da quest (Ctrl+E)")
        self.title_action=self._action("Título","F2",self._focus_title,tb); self.title_action.setToolTip("Editar título da quest (F2)")
        self.description_action=self._action("Desc.",None,self._focus_description,tb); self.description_action.setToolTip("Editar descrição da quest")
        self.dependencies_action=self._action("Deps",None,self._open_dependencies_editor,tb); self.dependencies_action.setToolTip("Editar dependências; com múltipla seleção abre edição em lote")
        self.tasks_action=self._action("Tasks",None,lambda:self._open_quest_editor_tab(2),tb); self.tasks_action.setToolTip("Editar Tasks da quest")
        self.rewards_action=self._action("Rewards",None,lambda:self._open_quest_editor_tab(3),tb); self.rewards_action.setToolTip("Editar Rewards da quest")
        self.copy_id_action=self._action("ID",None,self._copy_current_id,tb); self.copy_id_action.setToolTip("Copiar ID da quest")
        self.duplicate_action=self._action("⧉","Ctrl+D",self._duplicate_current,tb); self.duplicate_action.setToolTip("Duplicar quest selecionada (Ctrl+D)")
        self.delete_action=self._action("✕",None,self._delete_current,tb); self.delete_action.setToolTip("Excluir quest(s) selecionada(s) (Delete)")
        self.save_quest_action=self._action("Salvar","Ctrl+S",self._save_current_quest,tb); self.save_quest_action.setToolTip("Salvar alterações da quest (Ctrl+S)")
        self.quest_single_actions=[self.properties_action,self.title_action,self.description_action,self.tasks_action,self.rewards_action,self.copy_id_action,self.duplicate_action,self.save_quest_action]
        for a in self.quest_single_actions: a.setEnabled(False)
        self.dependencies_action.setEnabled(False); self.delete_action.setEnabled(False)

        # O status detalhado do projeto foi movido para a status bar para liberar largura na navbar.
        self.project_status=QLabel("Nenhum modpack")
        self.project_status.setObjectName("projectStatus")
        self.project_status.setToolTip("Selecione a pasta do modpack")
        self.statusBar().addPermanentWidget(self.project_status)

        # Quest Book hierarchy, closer to the in-game sidebar: groups -> chapters.
        left=QWidget(); ll=QVBoxLayout(left); ll.setContentsMargins(4,4,4,4); ll.setSpacing(4)
        head=QHBoxLayout(); title=QLabel("Quest Book"); title.setObjectName("panelTitle"); self.hide_left_btn=QPushButton("◀"); self.hide_left_btn.setObjectName("collapseButton"); self.hide_left_btn.setToolTip("Ocultar Quest Book"); self.hide_left_btn.setFixedWidth(34); self.hide_left_btn.clicked.connect(lambda:self._set_panel_visible("left",False)); head.addWidget(title); head.addStretch(1); head.addWidget(self.hide_left_btn); ll.addLayout(head)
        buttons=QHBoxLayout(); self.add_group=QPushButton("＋ Grupo"); self.add_chapter=QPushButton("＋ Capítulo"); self.edit_structure=QPushButton("Editar");
        for b in (self.add_group,self.add_chapter,self.edit_structure): buttons.addWidget(b)
        ll.addLayout(buttons)
        self.chapter_tree=QTreeWidget(); self.chapter_tree.setMinimumWidth(300); self.chapter_tree.setObjectName("chapterList"); self.chapter_tree.setHeaderHidden(True); self.chapter_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chapter_tree.currentItemChanged.connect(self._tree_selected); self.chapter_tree.customContextMenuRequested.connect(self._tree_context_menu); ll.addWidget(self.chapter_tree,1)
        self.add_group.clicked.connect(self._new_group); self.add_chapter.clicked.connect(self._new_chapter); self.edit_structure.clicked.connect(self._edit_selected_structure)

        self.canvas=QuestCanvas(); self.canvas.questSelected.connect(self._quest_selected); self.canvas.positionsCommitted.connect(self._quests_moved); self.canvas.deleteRequested.connect(self._delete_quest); self.canvas.deleteManyRequested.connect(self._delete_many_quests); self.canvas.duplicateRequested.connect(self._duplicate_quest); self.canvas.newQuestRequested.connect(self._new_quest_at); self.canvas.propertiesRequested.connect(self._show_properties); self.canvas.editTitleRequested.connect(lambda q:(self._quest_selected(q),self.props.focus_title())); self.canvas.editDescriptionRequested.connect(lambda q:(self._quest_selected(q),self.props.focus_description())); self.canvas.dependenciesRequested.connect(lambda q:(self._quest_selected(q),self._open_quest_editor_tab(1))); self.canvas.tasksRequested.connect(lambda q:(self._quest_selected(q),self._open_quest_editor_tab(2))); self.canvas.rewardsRequested.connect(lambda q:(self._quest_selected(q),self._open_quest_editor_tab(3))); self.canvas.copyIdRequested.connect(lambda q:(self._quest_selected(q),self._copy_current_id())); self.canvas.selectionChanged.connect(self._canvas_selection_changed); self.canvas.batchDependenciesRequested.connect(self._batch_dependencies)

        # Visual layout toolbar: multi-selection, alignment, distribution and snapping.
        layout_tb=QToolBar("Layout"); layout_tb.setMovable(False); self.addToolBarBreak(); self.addToolBar(layout_tb); self.layout_tb=layout_tb
        self.selection_label=QLabel("0 selecionadas"); self.selection_label.setObjectName("selectionStatus"); layout_tb.addWidget(self.selection_label); layout_tb.addSeparator()
        self.layout_actions=[]
        def la(text, tip, slot):
            a=QAction(text,self); a.setToolTip(tip); a.triggered.connect(slot); layout_tb.addAction(a); self.layout_actions.append(a); return a
        la("↤", "Alinhar à esquerda", lambda:self.canvas.align_selection("left")); la("↔", "Centralizar horizontalmente", lambda:self.canvas.align_selection("hcenter")); la("↦", "Alinhar à direita", lambda:self.canvas.align_selection("right")); layout_tb.addSeparator()
        la("↥", "Alinhar ao topo", lambda:self.canvas.align_selection("top")); la("↕", "Centralizar verticalmente", lambda:self.canvas.align_selection("vcenter")); la("↧", "Alinhar à base", lambda:self.canvas.align_selection("bottom")); layout_tb.addSeparator()
        la("⇆", "Distribuir horizontalmente", lambda:self.canvas.distribute_selection("x")); la("⇅", "Distribuir verticalmente", lambda:self.canvas.distribute_selection("y")); la("◎", "Juntar todos no centro", self.canvas.stack_selection_center); layout_tb.addSeparator()
        self.batch_deps_action=la("⛓", "Adicionar/remover a mesma dependência em todas as quests selecionadas", lambda:self._batch_dependencies(self.canvas.selected_quests())); layout_tb.addSeparator()
        layout_tb.addWidget(QLabel("Gap X")); self.gap_x=QDoubleSpinBox(); self.gap_x.setRange(0,100); self.gap_x.setDecimals(2); self.gap_x.setValue(1.0); self.gap_x.setSuffix(" u"); self.gap_x.setMaximumWidth(88); layout_tb.addWidget(self.gap_x); self.gap_x_btn=QPushButton("Aplicar"); self.gap_x_btn.clicked.connect(lambda:self.canvas.space_selection("x",self.gap_x.value())); layout_tb.addWidget(self.gap_x_btn)
        layout_tb.addWidget(QLabel("Gap Y")); self.gap_y=QDoubleSpinBox(); self.gap_y.setRange(0,100); self.gap_y.setDecimals(2); self.gap_y.setValue(1.0); self.gap_y.setSuffix(" u"); self.gap_y.setMaximumWidth(88); layout_tb.addWidget(self.gap_y); self.gap_y_btn=QPushButton("Aplicar"); self.gap_y_btn.clicked.connect(lambda:self.canvas.space_selection("y",self.gap_y.value())); layout_tb.addWidget(self.gap_y_btn); layout_tb.addSeparator()
        self.snap_check=QCheckBox("Snap"); self.snap_check.setToolTip("Encaixar movimentos na grade do FTB Quests"); layout_tb.addWidget(self.snap_check); self.snap_step=QDoubleSpinBox(); self.snap_step.setRange(.05,20); self.snap_step.setDecimals(2); self.snap_step.setValue(.5); self.snap_step.setSuffix(" u"); self.snap_step.setMaximumWidth(84); layout_tb.addWidget(self.snap_step)
        self.snap_check.toggled.connect(lambda v:self.canvas.set_snap(v,self.snap_step.value())); self.snap_step.valueChanged.connect(lambda v:self.canvas.set_snap(self.snap_check.isChecked(),v)); layout_tb.addSeparator()
        self.undo_layout_action=la("↶", "Desfazer última alteração (Ctrl+Z)", self._undo_global); self.redo_layout_action=la("↷", "Refazer alteração (Ctrl+Y)", self._redo_global)
        self.undo_layout_action.setShortcut(QKeySequence.Undo); self.undo_layout_action.setShortcutContext(Qt.ApplicationShortcut); self.addAction(self.undo_layout_action)
        self.redo_layout_action.setShortcut(QKeySequence.Redo); self.redo_layout_action.setShortcutContext(Qt.ApplicationShortcut); self.addAction(self.redo_layout_action)
        tb.addSeparator(); tb.addAction(self.undo_layout_action); tb.addAction(self.redo_layout_action)
        self.selection_tool_btn=QPushButton("▭ Seleção")
        self.selection_tool_btn.setObjectName("toolbarCompactButton")
        self.selection_tool_btn.setCheckable(True)
        self.selection_tool_btn.setToolTip("Seleção por área: clique e arraste no fundo. Ctrl+clique soma itens; Ctrl+Shift+arrastar seleciona área temporariamente; Espaço move a tela.")
        self.selection_tool_btn.toggled.connect(self.canvas.set_selection_tool)
        self.canvas.selectionToolChanged.connect(lambda v:self.selection_tool_btn.setChecked(v) if self.selection_tool_btn.isChecked()!=v else None)
        tb.addWidget(self.selection_tool_btn)
        self._canvas_selection_changed([]); self._history_actions_changed()

        self.left_panel=left
        self.props=QuestProperties(); self.props.setMinimumWidth(340); self.props.saveRequested.connect(self._save_quest); self.props.draftChanged.connect(self._draft_changed); self.props.navigateQuestRequested.connect(self._goto_quest_id)
        self.items=ItemBrowser(); self.items.itemActivated.connect(self.props.set_item)
        self.translations=TranslationEditor(); self.translations.saveRequested.connect(self._save_translations); self.translations.importRequested.connect(self._import_translations); self.translations.syncRequested.connect(self._open_translation_sync)
        self.problems=ProblemsPanel(); self.problems.problemActivated.connect(self._goto_problem)

        self.right_tabs=QTabWidget(); self.right_tabs.addTab(self.props,"Quest"); self.right_tabs.addTab(self.items,"Itens")
        self.right_panel=QWidget(); rpl=QVBoxLayout(self.right_panel); rpl.setContentsMargins(0,0,0,0); rpl.setSpacing(0)
        rhead=QHBoxLayout(); rhead.setContentsMargins(8,4,4,2); rtitle=QLabel("Inspetor"); rtitle.setObjectName("panelTitle"); self.hide_right_btn=QPushButton("▶"); self.hide_right_btn.setObjectName("collapseButton"); self.hide_right_btn.setToolTip("Ocultar Inspetor"); self.hide_right_btn.setFixedWidth(34); self.hide_right_btn.clicked.connect(lambda:self._set_panel_visible("right",False)); rhead.addWidget(rtitle); rhead.addStretch(1); rhead.addWidget(self.hide_right_btn); rpl.addLayout(rhead); rpl.addWidget(self.right_tabs,1)

        self.problems_panel=QWidget(); ppl=QVBoxLayout(self.problems_panel); ppl.setContentsMargins(0,0,0,0); ppl.setSpacing(0)
        phead=QHBoxLayout(); phead.setContentsMargins(8,2,4,0); ptitle=QLabel("Problemas"); ptitle.setObjectName("panelTitle"); self.hide_problems_btn=QPushButton("⌄"); self.hide_problems_btn.setObjectName("collapseButton"); self.hide_problems_btn.setToolTip("Ocultar Problemas"); self.hide_problems_btn.setFixedWidth(34); self.hide_problems_btn.clicked.connect(lambda:self._set_panel_visible("problems",False)); phead.addWidget(ptitle); phead.addStretch(1); phead.addWidget(self.hide_problems_btn); ppl.addLayout(phead); ppl.addWidget(self.problems,1)

        self.top_splitter=QSplitter(Qt.Horizontal); self.top_splitter.setChildrenCollapsible(True); self.top_splitter.addWidget(self.left_panel); self.top_splitter.addWidget(self.canvas); self.top_splitter.addWidget(self.right_panel); self.top_splitter.setSizes([300,930,430])
        self.tree_splitter=QSplitter(Qt.Vertical); self.tree_splitter.setChildrenCollapsible(True); self.tree_splitter.addWidget(self.top_splitter); self.tree_splitter.addWidget(self.problems_panel); self.tree_splitter.setSizes([760,160])
        self.main_tabs=QTabWidget(); self.main_tabs.addTab(self.tree_splitter,"Quest Book"); self.main_tabs.addTab(self.translations,"Traduções"); self.setCentralWidget(self.main_tabs)
        self._build_view_controls(tb)
        self._build_tools_controls(tb)
        self._build_help_menu()
        self._restore_ui_state()
        self.layout_tb.setVisible(not self.contextual_layout)

    # ---------- responsive workspace / panels ----------
    def _toolbar_toggle_button(self, toolbar, text, action, tooltip):
        btn=QToolButton(); btn.setObjectName("toolbarToggleButton"); btn.setText(text); btn.setCheckable(True); btn.setChecked(action.isChecked()); btn.setToolTip(tooltip)
        btn.toggled.connect(lambda v,a=action: a.setChecked(v) if a.isChecked()!=v else None)
        action.toggled.connect(lambda v,b=btn: b.setChecked(v) if b.isChecked()!=v else None)
        toolbar.addWidget(btn); return btn

    def _toolbar_action_button(self, toolbar, text, slot, tooltip):
        btn=QToolButton(); btn.setObjectName("toolbarActionButton"); btn.setText(text); btn.setToolTip(tooltip); btn.clicked.connect(slot); toolbar.addWidget(btn); return btn

    def _build_view_controls(self, toolbar):
        # Ações continuam existindo (atalhos/estado), mas 0.9.1 remove o menu Visualizar:
        # os controles principais ficam sempre visíveis em formato compacto na navbar.
        self.view_left_action=QAction("Quest Book lateral",self,checkable=True); self.view_left_action.setShortcut(QKeySequence("Ctrl+1")); self.view_left_action.setChecked(True); self.view_left_action.toggled.connect(lambda v:self._set_panel_visible("left",v))
        self.view_right_action=QAction("Inspetor Quest / Itens",self,checkable=True); self.view_right_action.setShortcut(QKeySequence("Ctrl+2")); self.view_right_action.setChecked(True); self.view_right_action.toggled.connect(lambda v:self._set_panel_visible("right",v))
        self.view_problems_action=QAction("Painel de Problemas",self,checkable=True); self.view_problems_action.setShortcut(QKeySequence("Ctrl+3")); self.view_problems_action.setChecked(True); self.view_problems_action.toggled.connect(lambda v:self._set_panel_visible("problems",v))
        self.contextual_layout_action=QAction("Layout só com múltipla seleção",self,checkable=True); self.contextual_layout_action.setChecked(True); self.contextual_layout_action.toggled.connect(self._set_contextual_layout)
        self.auto_inspector_action=QAction("Abrir Inspetor ao selecionar quest",self,checkable=True); self.auto_inspector_action.setChecked(True); self.auto_inspector_action.toggled.connect(lambda v:setattr(self,"auto_show_inspector",bool(v)))
        self.auto_compact_action=QAction("Modo responsivo automático",self,checkable=True); self.auto_compact_action.setChecked(True); self.auto_compact_action.toggled.connect(self._set_auto_compact)
        self.view_quest_tab_action=QAction("Quest",self,checkable=True); self.view_quest_tab_action.setChecked(True); self.view_quest_tab_action.toggled.connect(lambda v:self._set_tab_visible(self.right_tabs,0,v,self.view_quest_tab_action))
        self.view_items_tab_action=QAction("Itens",self,checkable=True); self.view_items_tab_action.setChecked(True); self.view_items_tab_action.toggled.connect(lambda v:self._set_tab_visible(self.right_tabs,1,v,self.view_items_tab_action))
        self.view_translations_tab_action=QAction("Traduções",self,checkable=True); self.view_translations_tab_action.setChecked(True); self.view_translations_tab_action.toggled.connect(lambda v:self._set_tab_visible(self.main_tabs,1,v,self.view_translations_tab_action))
        self.focus_action=QAction("Modo foco no canvas",self,checkable=True); self.focus_action.setShortcut(QKeySequence("F10")); self.focus_action.toggled.connect(self._focus_canvas)

        toolbar.addSeparator()
        self.left_quick=self._toolbar_toggle_button(toolbar,"Book",self.view_left_action,"Mostrar/ocultar Quest Book lateral (Ctrl+1)")
        self.right_quick=self._toolbar_toggle_button(toolbar,"Insp.",self.view_right_action,"Mostrar/ocultar Inspetor (Ctrl+2)")
        self.problems_quick=self._toolbar_toggle_button(toolbar,"Erros",self.view_problems_action,"Mostrar/ocultar painel de Problemas (Ctrl+3)")
        self.responsive_quick=self._toolbar_toggle_button(toolbar,"Resp.",self.auto_compact_action,"Responsividade automática: esconde painéis em telas menores")
        self.focus_quick=self._toolbar_toggle_button(toolbar,"Foco",self.focus_action,"Modo foco: só o canvas (F10)")
        for a in (self.view_left_action,self.view_right_action,self.view_problems_action,self.focus_action): self.addAction(a)
        self.main_tabs.currentChanged.connect(self._main_tab_changed)

    def _build_tools_controls(self, toolbar):
        # Ferramentas importantes agora são botões diretos — sem abrir o menu Ferramentas.
        toolbar.addSeparator()
        self.assets_quick=self._toolbar_action_button(toolbar,"Assets",self._open_asset_library,"Biblioteca universal: abrir JARs/KubeJS sem precisar abrir modpack")
        self.converter_quick=self._toolbar_action_button(toolbar,"⇄ Converter",lambda:self._open_converter(1),"Conversão avançada de storage SNBT ↔ JSON5")
        self.port_quick=self._toolbar_action_button(toolbar,"Port",lambda:self._open_converter(0),"Port Universal: FTB 1.20 → 1.21 → 26.1.2 e 1.21 ↔ 26.1.2")
        self.lang_quick=self._toolbar_action_button(toolbar,"Lang",lambda:self._open_converter(3),"Lang Splitter, merge e preenchimento de traduções")
        self.translation_quick=self._toolbar_action_button(toolbar,"Tradução",self._open_translation_sync,"Central de Tradução: importar lang atualizado e localizar strings quebradas")
        self.theme_quick=self._toolbar_action_button(toolbar,"Tema",self._open_theme,"Personalizar tema e cores do Alpha Quest Editor")
        self.dependency_map_quick=self._toolbar_action_button(toolbar,"Deps em lote",self._open_dependency_mapper,"Mapa de Dependências: capture pré-requisitos e quem recebe usando a seleção do canvas")


    def _build_help_menu(self):
        # Keep the single-row workspace: diagnostics live in a compact navbar button
        # instead of adding a traditional menubar above the canvas.
        menu=QMenu(self)
        logs_action=QAction("Abrir pasta de logs",self); logs_action.triggered.connect(self._open_logs_folder); menu.addAction(logs_action)
        diag_action=QAction("Copiar diagnóstico",self); diag_action.triggered.connect(self._copy_diagnostics); menu.addAction(diag_action)
        vanilla_action=QAction("Configurar JAR vanilla / texturas…",self); vanilla_action.triggered.connect(self._choose_vanilla_client_jar); menu.addAction(vanilla_action)
        menu.addSeparator()
        about_action=QAction("Sobre",self); about_action.triggered.connect(self._show_about); menu.addAction(about_action)
        btn=QToolButton(); btn.setObjectName("toolbarActionButton"); btn.setText("Ajuda"); btn.setToolTip("Logs, diagnóstico e informações da versão"); btn.setMenu(menu); btn.setPopupMode(QToolButton.InstantPopup); self.main_tb.addWidget(btn); self.help_quick=btn

    def _open_logs_folder(self):
        path=logs_dir(); QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _copy_diagnostics(self):
        text=diagnostic_text(self.book,self.mods); QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Diagnóstico copiado. Cole no GitHub/Discord ao reportar um bug.")


    def _choose_vanilla_client_jar(self):
        start=str(self.settings.value("assets/vanilla_client_jar", "") or "")
        path,_=QFileDialog.getOpenFileName(self,"Selecionar JAR cliente do Minecraft",start,"Minecraft / Java archive (*.jar);;Todos (*.*)")
        if not path:return
        candidate=Path(path)
        if not ModIndex._looks_like_vanilla_client_jar(candidate):
            return QMessageBox.warning(self,"JAR vanilla","Esse arquivo não parece ser o JAR cliente do Minecraft com assets/textures.\n\nEscolha o JAR que contém assets/minecraft/textures/item/.")
        self.settings.setValue("assets/vanilla_client_jar",str(candidate))
        self.statusBar().showMessage(f"JAR vanilla configurado: {candidate.name}. Reindexando…")
        if self.book:self.scan_mods(force=True)

    def _show_about(self):
        QMessageBox.about(self,"Alpha Quest Editor",f"Alpha Quest Editor {APP_VERSION}\n\nUniversal Minecraft Quest Authoring Tool\n\nEsta versão adiciona o Port Universal: FTB 1.20 → 1.21 → 26.1.2, 1.20 → 26.1.2 direto e 1.21 ↔ 26.1.2, mantendo os recursos de estabilidade e edição.")

    def _open_asset_library(self):
        if self.asset_library is None:
            self.asset_library = AssetLibraryDialog(self)
        self.asset_library.show()
        self.asset_library.raise_()
        self.asset_library.activateWindow()

    def _open_dependency_mapper(self):
        if not self.book:
            return QMessageBox.information(self, "Mapa de Dependências", "Abra um modpack/Quest Book primeiro.")
        if self.dependency_mapper is None:
            self.dependency_mapper = DependencyMapperDialog(
                lambda: self.canvas.selected_quests(),
                lambda: self.book.quest_by_id if self.book else {},
                self._quest_display_title,
                self,
            )
            self.dependency_mapper.applyRequested.connect(self._apply_dependency_map)
        self.dependency_mapper.show()
        self.dependency_mapper.raise_()
        self.dependency_mapper.activateWindow()

    def _apply_dependency_map(self, prerequisite_ids, dependent_ids, mode):
        if not self.book:
            return
        prereqs = [qid for qid in dict.fromkeys(prerequisite_ids or []) if qid in self.book.quest_by_id]
        dependents = [qid for qid in dict.fromkeys(dependent_ids or []) if qid in self.book.quest_by_id]
        overlap = set(prereqs) & set(dependents)
        if not prereqs or not dependents:
            return QMessageBox.information(self, "Mapa de Dependências", "Capture Dependências e Quem recebe antes de aplicar.")
        if overlap:
            return QMessageBox.warning(self, "Mapa de Dependências", "Uma quest não pode ser dependência dela mesma. Remova as quests repetidas entre os dois lados.")

        verb = "Adicionar" if mode == "add" else "Remover"
        relation_count = len(prereqs) * len(dependents)
        ans = QMessageBox.question(
            self,
            "Confirmar mapa de dependências",
            f"{verb} {len(prereqs)} dependência(s) em {len(dependents)} quest(s)?\n\n"
            f"Relações processadas: {relation_count}\n"
            "Dependências existentes serão preservadas no modo Adicionar.\n\n"
            "A operação inteira poderá ser desfeita com Ctrl+Z.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ans != QMessageBox.Yes:
            return

        before = self._history_before()
        backup_questbook(self.book.quest_root)
        self._mark_own_write()
        dependent_quests = [self.book.quest_by_id[qid] for qid in dependents]
        ok, changed = self.book.map_dependencies(prereqs, dependents, mode)
        if not changed:
            return self.statusBar().showMessage("Mapa de dependências: nenhuma relação precisou ser alterada.")
        label = ("Adicionar" if mode == "add" else "Remover") + f" mapa de dependências ({len(prereqs)} → {changed})"
        self._history_commit(label, before)
        self.reload_questbook()
        self._history_actions_changed()
        if self.dependency_mapper is not None:
            self.dependency_mapper._refresh()
        self.statusBar().showMessage(
            f"{label} • {relation_count} relação(ões) processadas • Ctrl+Z desfaz tudo"
            if ok else f"{label}, com falhas parciais; confira Problemas"
        )


    def _open_translation_sync(self):
        if not self.book:
            return QMessageBox.information(self, "Central de Tradução", "Abra um modpack/Quest Book primeiro.")
        if self.translation_sync is None:
            self.translation_sync = TranslationSyncDialog(self.book, self)
            self.translation_sync.applyRequested.connect(self._apply_translation_sync)
        else:
            self.translation_sync.book = self.book
            self.translation_sync._load_locales()
        self.translation_sync.show()
        self.translation_sync.raise_()
        self.translation_sync.activateWindow()

    def _apply_translation_sync(self, locale, records):
        if not self.book or not records:
            return
        locale = str(locale or "pt_br").replace("-", "_").lower()
        from ..core.lang import load_locale_tree
        current = load_locale_tree(self.book.quest_root, locale, self.book.storage_format)
        changed = []
        for row in records:
            key = str(row.get("key", "")).strip()
            value = str(row.get("value", "")).replace("\r\n", "\n").replace("\r", "\n")
            if not key or current.get(key, "") == value:
                continue
            changed.append((key, value))
        if not changed:
            return QMessageBox.information(self, "Central de Tradução", "Nenhuma alteração nova foi encontrada.")
        ans = QMessageBox.question(
            self, "Aplicar arquivo de tradução",
            f"Aplicar {len(changed)} tradução(ões) ao locale {locale}?\n\n"
            "O Alpha vai localizar o arquivo físico correto para cada chave (flat/split SNBT ou JSON5).\n"
            "Um backup será criado e Ctrl+Z desfaz a importação inteira.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if ans != QMessageBox.Yes:
            return
        before = self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write()
        for key, value in changed:
            self.book.save_translation_locale(locale, key, value)
        self._history_commit(f"Importar lang {locale} ({len(changed)} strings)", before)
        self.reload_questbook(); self.main_tabs.setCurrentWidget(self.translations); self._history_actions_changed()
        if self.translation_sync is not None:
            self.translation_sync.book = self.book
            self.translation_sync._load_locales()
        self.statusBar().showMessage(f"{len(changed)} tradução(ões) importada(s) em {locale}. Ctrl+Z desfaz tudo.")

    def _open_converter(self, initial_tab=0):
        dlg = ConverterDialog(self.book.quest_root if self.book else None, self, initial_tab=initial_tab)
        dlg.projectChanged.connect(self.reload_questbook)
        dlg.exec()

    def _open_theme(self):
        preset, current = load_theme(self.settings)
        dlg = ThemeDialog(preset, current, self)
        dlg.previewRequested.connect(apply_theme)
        if dlg.exec():
            preset, chosen = dlg.result_theme(); save_theme(preset, chosen, self.settings); apply_theme(chosen)
            self.statusBar().showMessage(f"Tema salvo: {preset}")
        else:
            apply_theme(dlg.initial_theme())

    def _set_tab_visible(self,tabs,index,visible,action=None):
        # Qt 6 supports hidden tabs without destroying their widgets/state.
        tabs.setTabVisible(index,bool(visible))
        if action and action.isChecked()!=bool(visible): action.blockSignals(True); action.setChecked(bool(visible)); action.blockSignals(False)

    def _sync_view_checks(self):
        pairs=(
            (getattr(self,"view_left_action",None),getattr(self,"left_quick",None),self.left_panel.isVisible()),
            (getattr(self,"view_right_action",None),getattr(self,"right_quick",None),self.right_panel.isVisible()),
            (getattr(self,"view_problems_action",None),getattr(self,"problems_quick",None),self.problems_panel.isVisible()),
        )
        for action,button,value in pairs:
            if action and action.isChecked()!=value:
                action.blockSignals(True); action.setChecked(value); action.blockSignals(False)
            if button and button.isChecked()!=value:
                button.blockSignals(True); button.setChecked(value); button.blockSignals(False)

    def _set_panel_visible(self,name,visible):
        panel={"left":self.left_panel,"right":self.right_panel,"problems":self.problems_panel}.get(name)
        if not panel:return
        self._preferred_visibility[name]=bool(visible)
        panel.setVisible(bool(visible)); self._sync_view_checks()
        if visible:
            if name=="left" and self.top_splitter.sizes()[0]<80:self.top_splitter.setSizes([300,max(500,self.top_splitter.sizes()[1]),self.top_splitter.sizes()[2]])
            elif name=="right" and self.top_splitter.sizes()[2]<80:self.top_splitter.setSizes([self.top_splitter.sizes()[0],max(500,self.top_splitter.sizes()[1]),420])
            elif name=="problems" and self.tree_splitter.sizes()[1]<60:self.tree_splitter.setSizes([max(500,self.tree_splitter.sizes()[0]),160])

    def _set_contextual_layout(self,enabled):
        self.contextual_layout=bool(enabled)
        n=len(self.canvas.selected_quests()) if hasattr(self,"canvas") else 0
        self.layout_tb.setVisible((n>=2) if self.contextual_layout else True)

    def _set_auto_compact(self,enabled):
        self.auto_compact=bool(enabled); self._apply_responsive_layout()

    def _main_tab_changed(self,index):
        if self.contextual_layout:
            self.layout_tb.setVisible(index==0 and len(self.canvas.selected_quests())>=2 and self._focus_mode_state is None)
        else:self.layout_tb.setVisible(index==0 and self._focus_mode_state is None)

    def _focus_canvas(self,enabled):
        if enabled:
            self._focus_mode_state=(self.left_panel.isVisible(),self.right_panel.isVisible(),self.problems_panel.isVisible(),self.layout_tb.isVisible())
            self.left_panel.hide(); self.right_panel.hide(); self.problems_panel.hide(); self.layout_tb.hide(); self.main_tabs.setCurrentIndex(0)
        else:
            state=self._focus_mode_state or (True,True,True,False); self._focus_mode_state=None
            self.left_panel.setVisible(state[0]); self.right_panel.setVisible(state[1]); self.problems_panel.setVisible(state[2])
            if self.contextual_layout:self.layout_tb.setVisible(len(self.canvas.selected_quests())>=2)
            else:self.layout_tb.setVisible(state[3])
        self._sync_view_checks()

    def _restore_default_layout(self):
        if self._focus_mode_state is not None:self.focus_action.setChecked(False)
        self._preferred_visibility={"left":True,"right":True,"problems":True}; self.left_panel.show(); self.right_panel.show(); self.problems_panel.show(); self.top_splitter.setSizes([300,900,430]); self.tree_splitter.setSizes([740,180])
        self.contextual_layout=True; self.contextual_layout_action.setChecked(True); self.auto_show_inspector=True; self.auto_inspector_action.setChecked(True); self.auto_compact=True; self.auto_compact_action.setChecked(True)
        self.view_quest_tab_action.setChecked(True); self.view_items_tab_action.setChecked(True); self.view_translations_tab_action.setChecked(True); self._sync_view_checks(); self._apply_responsive_layout()

    def _apply_responsive_layout(self):
        if not hasattr(self,"top_splitter") or self._focus_mode_state is not None or not self.auto_compact:return
        w=self.width(); h=self.height()
        # Keep the canvas useful on smaller displays. This is reversible when the window grows again.
        show_left=self._preferred_visibility.get("left",True) and w>=980
        show_right=self._preferred_visibility.get("right",True) and (w>=1150 or self.current_quest is not None)
        show_problems=self._preferred_visibility.get("problems",True) and w>=1150 and h>=720
        self.left_panel.setVisible(show_left); self.right_panel.setVisible(show_right); self.problems_panel.setVisible(show_problems)
        self._sync_view_checks()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"auto_compact") and self.auto_compact: QTimer.singleShot(0,self._apply_responsive_layout)

    def closeEvent(self,event):
        # A worker thread must not be destroyed while indexing a large JAR. Ask it
        # to stop and wait briefly for the current archive to finish safely.
        self._cancel_active_scan(8000)
        try:
            self.settings.setValue("window/geometry",self.saveGeometry())
            self.settings.setValue("splitter/top",self.top_splitter.sizes())
            self.settings.setValue("splitter/tree",self.tree_splitter.sizes())
            self.settings.setValue("view/left",self._preferred_visibility.get("left",True))
            self.settings.setValue("view/right",self._preferred_visibility.get("right",True))
            self.settings.setValue("view/problems",self._preferred_visibility.get("problems",True))
            self.settings.setValue("view/contextual_layout",self.contextual_layout)
            self.settings.setValue("view/auto_inspector",self.auto_show_inspector)
            self.settings.setValue("view/auto_compact",self.auto_compact)
            self.settings.setValue("tabs/quest",self.right_tabs.isTabVisible(0)); self.settings.setValue("tabs/items",self.right_tabs.isTabVisible(1)); self.settings.setValue("tabs/translations",self.main_tabs.isTabVisible(1))
        except Exception: pass
        super().closeEvent(event)

    @staticmethod
    def _setting_bool(value,default=True):
        if value is None:return default
        if isinstance(value,bool):return value
        return str(value).strip().lower() in ("1","true","yes","on")

    def _restore_ui_state(self):
        geo=self.settings.value("window/geometry")
        if geo:self.restoreGeometry(geo)
        top=self.settings.value("splitter/top"); tree=self.settings.value("splitter/tree")
        try:
            if top:self.top_splitter.setSizes([int(x) for x in top])
            if tree:self.tree_splitter.setSizes([int(x) for x in tree])
        except Exception: pass
        self.contextual_layout=self._setting_bool(self.settings.value("view/contextual_layout"),True); self.contextual_layout_action.setChecked(self.contextual_layout)
        self.auto_show_inspector=self._setting_bool(self.settings.value("view/auto_inspector"),True); self.auto_inspector_action.setChecked(self.auto_show_inspector)
        self.auto_compact=self._setting_bool(self.settings.value("view/auto_compact"),True); self.auto_compact_action.setChecked(self.auto_compact)
        self._set_tab_visible(self.right_tabs,0,self._setting_bool(self.settings.value("tabs/quest"),True),self.view_quest_tab_action)
        self._set_tab_visible(self.right_tabs,1,self._setting_bool(self.settings.value("tabs/items"),True),self.view_items_tab_action)
        self._set_tab_visible(self.main_tabs,1,self._setting_bool(self.settings.value("tabs/translations"),True),self.view_translations_tab_action)
        self._preferred_visibility={
            "left":self._setting_bool(self.settings.value("view/left"),True),
            "right":self._setting_bool(self.settings.value("view/right"),True),
            "problems":self._setting_bool(self.settings.value("view/problems"),True),
        }
        self.left_panel.setVisible(self._preferred_visibility["left"]); self.right_panel.setVisible(self._preferred_visibility["right"]); self.problems_panel.setVisible(self._preferred_visibility["problems"]); self._sync_view_checks()
        QTimer.singleShot(0,self._apply_responsive_layout)

    def _cancel_active_scan(self, wait_ms=8000):
        worker=self._scan_worker; thread=self._scan_thread
        if worker is not None:
            worker.request_cancel()
        if thread is not None and thread.isRunning():
            thread.quit()
            return bool(thread.wait(int(wait_ms)))
        return True

    def choose_modpack(self):
        path=QFileDialog.getExistingDirectory(self,"Selecione a pasta raiz do modpack")
        if path:self.open_modpack(Path(path))

    def open_modpack(self,root:Path):
        """Open a project without discarding the current one if parsing fails."""
        self._cancel_active_scan()
        try:
            candidate=QuestBook(Path(root)); candidate.load()
        except Exception as exc:
            logging.getLogger(__name__).exception("Falha ao abrir Quest Book em %s", root)
            QMessageBox.critical(self,"Não foi possível abrir",f"O Quest Book não pôde ser carregado.\n\n{exc}\n\nO projeto atual foi mantido. Veja Ajuda → Abrir pasta de logs para detalhes.")
            return
        self.book=candidate; self.mods=ModIndex(); self.history.clear(); self.current_chapter=None; self.current_quest=None
        self._populate_chapters(); self.translations.set_book(self.book); self.items.set_index(self.mods); self.props.set_item_index(self.mods); self._reset_watcher(); self._validate(); self._update_project_status(); self._history_actions_changed()
        self.statusBar().showMessage("Quest Book carregado. Indexando assets em segundo plano…")
        self.scan_mods(force=False)

    def _update_project_status(self):
        if not self.book:return
        qn=sum(len(c.quests) for c in self.book.chapters); vanilla=sum(1 for k in self.mods.items if k.startswith("minecraft:")); modded=len(self.mods.items)-vanilla
        fmt = f"{self.book.storage_format.upper()} / {self.mods.minecraft_version if self.mods.minecraft_version != 'auto' else 'versão automática'}"
        total_items=vanilla+modded
        full=f"{self.book.root.name} • {fmt} • {qn} quests • {vanilla} vanilla + {modded} modded • {len(self.mods.quest_shapes)} shapes"
        compact=f"{fmt} • {qn}Q • {total_items} itens • {len(self.mods.quest_shapes)} shapes"
        self.project_status.setText(compact); self.project_status.setToolTip(full)

    def scan_mods(self, force: bool = False):
        """Index assets outside the GUI thread and keep cache hits invisible.

        0.9.6 showed a progress window immediately, even for a cache hit, and used
        Python lambdas as cross-thread signal targets. On some Windows/PySide6
        combinations this could leave the window looking frozen at 100%. The
        hotfix connects worker signals directly to MainWindow slots and only lets
        QProgressDialog appear when the job actually takes noticeable time.
        """
        if not self.book:return
        if self._scan_thread is not None and self._scan_thread.isRunning():
            self.statusBar().showMessage("A indexação já está em andamento.")
            return
        self.index_action.setEnabled(False)
        dlg=QProgressDialog("Preparando índice de assets…","Cancelar",0,100,self)
        dlg.setWindowModality(Qt.NonModal); dlg.setMinimumDuration(900); dlg.setAutoClose(False); dlg.setAutoReset(False); dlg.setValue(0)
        scan_root=Path(self.book.root).resolve()
        manual_jar=str(self.settings.value("assets/vanilla_client_jar", "") or "").strip()
        thread=QThread(self); worker=ModScanWorker(scan_root,force=force,vanilla_jar=manual_jar or None); worker.moveToThread(thread)
        self._scan_thread=thread; self._scan_worker=worker; self._scan_dialog=dlg; self._scan_root=scan_root
        thread.started.connect(worker.run)
        # Bound QObject slots force queued delivery back to the GUI thread.
        worker.progress.connect(self._scan_progress, Qt.QueuedConnection)
        worker.finished.connect(self._scan_finished, Qt.QueuedConnection)
        worker.cancelled.connect(self._scan_cancelled, Qt.QueuedConnection)
        worker.failed.connect(self._scan_failed, Qt.QueuedConnection)
        worker.finished.connect(worker.deleteLater); worker.cancelled.connect(worker.deleteLater); worker.failed.connect(worker.deleteLater)
        worker.finished.connect(thread.quit); worker.cancelled.connect(thread.quit); worker.failed.connect(thread.quit)
        thread.finished.connect(self._scan_cleanup_current)
        dlg.canceled.connect(worker.request_cancel)
        thread.start()

    def _scan_progress(self,i,total,name):
        dialog=self._scan_dialog
        if dialog is None:return
        dialog.setLabelText(f"Indexando {name}")
        value=int(i/max(1,total)*100)
        # Do not force-show the dialog. QProgressDialog honours minimumDuration
        # and cache hits therefore complete without flashing/focusing a window.
        dialog.setValue(value)
        self.statusBar().showMessage(f"Indexando assets: {name} ({value}%)")

    def _scan_finished(self,index):
        scan_root=self._scan_root
        if not self.book or scan_root is None or Path(self.book.root).resolve()!=Path(scan_root):
            return
        # Close the progress surface before refreshing models; this keeps Windows
        # responsive even while Qt applies the new index to visible widgets.
        if self._scan_dialog:self._scan_dialog.close()
        self.mods=index; self.mods.register_questbook_icons(self.book)
        self.items.set_index(self.mods); self.props.set_item_index(self.mods); self.props.set_shapes(self.mods.quest_shapes.keys())
        if self.current_chapter:self.canvas.load_chapter(self.current_chapter,self._icon,self._quest_display_title,self._shape_icon,preserve_view=True)
        self._validate(); self._update_project_status()
        vanilla=sum(1 for k in self.mods.items if k.startswith("minecraft:"))
        texture_note=getattr(self.mods,"vanilla_catalog_status","")
        if self.mods.loaded_from_cache:self.statusBar().showMessage(f"Índice carregado do cache: {len(self.mods.items)} itens • {texture_note}")
        elif self.mods.errors:self.statusBar().showMessage(f"Índice concluído com {len(self.mods.errors)} aviso(s). {len(self.mods.items)} itens • {texture_note}")
        else:self.statusBar().showMessage(f"Índice concluído: {len(self.mods.items)} itens ({vanilla} vanilla) • {texture_note}")

    def _scan_cancelled(self):
        if self._scan_dialog:self._scan_dialog.close()
        self.statusBar().showMessage("Indexação cancelada. O Quest Book continua disponível para edição.")

    def _scan_failed(self,message,trace):
        scan_root=self._scan_root
        logging.getLogger(__name__).error("Falha na indexação de assets (%s): %s\n%s",scan_root,message,trace)
        if scan_root is not None and self.book and Path(self.book.root).resolve()!=Path(scan_root):
            return
        if self._scan_dialog:self._scan_dialog.close()
        QMessageBox.warning(self,"Indexação de assets",f"O Quest Book foi aberto, mas a indexação dos itens/assets falhou.\n\n{message}\n\nVocê ainda pode editar o projeto e tentar Indexar novamente. Detalhes foram gravados no log.")

    def _scan_cleanup_current(self):
        dialog=self._scan_dialog; thread=self._scan_thread
        if dialog is not None:
            try:dialog.close(); dialog.deleteLater()
            except RuntimeError:pass
        self._scan_dialog=None; self._scan_worker=None; self._scan_thread=None; self._scan_root=None
        if hasattr(self,"index_action"):self.index_action.setEnabled(bool(self.book))
        if thread is not None:thread.deleteLater()

    def reload_questbook(self):
        if not self.book:return
        selected_ch=self.current_chapter.chapter_id if self.current_chapter else ""; selected_q=self._select_after_reload or (self.current_quest.quest_id if self.current_quest else ""); self._select_after_reload=""
        try:
            candidate=QuestBook(self.book.root); candidate.load()
        except Exception as exc:
            logging.getLogger(__name__).exception("Falha ao recarregar Quest Book")
            self.statusBar().showMessage("Falha ao recarregar: mantendo a última versão válida em memória.")
            QMessageBox.warning(self,"Recarregamento bloqueado",f"Uma alteração externa deixou algum arquivo inválido.\n\n{exc}\n\nO Alpha manteve a última versão válida em memória para evitar perder seu trabalho. Corrija o arquivo e recarregue novamente.")
            return
        self.book=candidate; self.mods.register_questbook_icons(self.book); self.items.set_index(self.mods); self.props.set_item_index(self.mods); self._populate_chapters(selected_ch); self.translations.set_book(self.book); self.props.set_shapes(self.mods.quest_shapes.keys()); self._validate(); self._reset_watcher(); self._update_project_status()
        if self.translation_sync is not None:
            self.translation_sync.book=self.book; self.translation_sync._load_locales()
        if self.dependency_mapper is not None:
            self.dependency_mapper._refresh()
        if selected_q and selected_q in self.book.quest_by_id:self._select_quest_in_book(self.book.quest_by_id[selected_q])

    # ---------- left hierarchy ----------
    def _populate_chapters(self,select_id=""):
        self.chapter_tree.clear()
        if not self.book:return
        group_nodes={}
        for g in self.book.chapter_groups:
            gi=QTreeWidgetItem([g.title]); gi.setData(0,ROLE_KIND,"group"); gi.setData(0,ROLE_OBJECT,g); gi.setToolTip(0,f"Grupo\n{g.group_id}"); self.chapter_tree.addTopLevelItem(gi); group_nodes[g.group_id]=gi
        ungrouped=None; target=None
        for ch in sorted(self.book.chapters,key=lambda c:(c.group_id,c.order_index,c.filename)):
            parent=group_nodes.get(ch.group_id)
            if parent is None:
                if ungrouped is None:
                    ungrouped=QTreeWidgetItem(["Sem grupo"]); ungrouped.setData(0,ROLE_KIND,"root"); self.chapter_tree.addTopLevelItem(ungrouped)
                parent=ungrouped
            ci=QTreeWidgetItem([f"{ch.title}   ({len(ch.quests)})"]); ci.setData(0,ROLE_KIND,"chapter"); ci.setData(0,ROLE_OBJECT,ch); ci.setToolTip(0,f"{ch.source_file.name}\n{ch.chapter_id}"); parent.addChild(ci)
            if ch.chapter_id==select_id:target=ci
        self.chapter_tree.expandAll()
        if target:self.chapter_tree.setCurrentItem(target)
        else:
            for i in range(self.chapter_tree.topLevelItemCount()):
                top=self.chapter_tree.topLevelItem(i)
                if top.childCount(): self.chapter_tree.setCurrentItem(top.child(0)); break
    def _tree_selected(self,item,previous=None):
        if not item:return
        if item.data(0,ROLE_KIND)!="chapter":return
        ch=item.data(0,ROLE_OBJECT)
        if not ch:return
        self.current_chapter=ch; self.current_quest=None; self.props.set_all_quests([q for c in self.book.chapters for q in c.quests] if self.book else []); self.props.set_quest(None); self.canvas.load_chapter(ch,self._icon,self._quest_display_title,self._shape_icon)
    def _selected_structure(self):
        it=self.chapter_tree.currentItem(); return (it.data(0,ROLE_KIND),it.data(0,ROLE_OBJECT)) if it else ("",None)
    def _tree_context_menu(self,pos):
        item=self.chapter_tree.itemAt(pos); menu=QMenu(self)
        if item:
            self.chapter_tree.setCurrentItem(item); kind=item.data(0,ROLE_KIND)
            if kind=="group":
                menu.addAction("＋ Novo capítulo neste grupo",self._new_chapter); menu.addAction("✦ Editar grupo",self._edit_selected_structure); menu.addSeparator(); menu.addAction("Excluir grupo",self._delete_selected_structure)
            elif kind=="chapter":
                menu.addAction("＋ Nova Quest",self._new_quest_center); menu.addAction("✦ Editar capítulo",self._edit_selected_structure); menu.addSeparator(); menu.addAction("Excluir capítulo",self._delete_selected_structure)
            else: menu.addAction("＋ Novo capítulo",self._new_chapter)
        else:
            menu.addAction("＋ Novo grupo",self._new_group); menu.addAction("＋ Novo capítulo",self._new_chapter)
        menu.exec(self.chapter_tree.viewport().mapToGlobal(pos))
    def _new_group(self):
        if not self.book:return
        dlg=GroupDialog(parent=self)
        if not dlg.exec():return
        before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write(); gid=self.book.create_group(dlg.value()["title"])
        if gid:self._history_commit("Criar grupo",before); self.reload_questbook(); self.statusBar().showMessage("Grupo criado.")
        else:QMessageBox.warning(self,"Falha","Não consegui criar o grupo no arquivo de grupos.")
    def _new_chapter(self):
        if not self.book:return
        dlg=ChapterDialog(self.book.chapter_groups,parent=self)
        kind,obj=self._selected_structure()
        if kind=="group":
            idx=dlg.group.findData(obj.group_id); dlg.group.setCurrentIndex(max(0,idx))
        if not dlg.exec():return
        v=dlg.value(); before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write(); cid=self.book.create_chapter(v["title"],v["filename"],v["group_id"])
        if cid:self._history_commit("Criar capítulo",before); self.book.load(); self._populate_chapters(cid); self.translations.set_book(self.book); self._reset_watcher(); self.statusBar().showMessage("Capítulo criado.")
        else:QMessageBox.warning(self,"Falha","Não consegui criar o capítulo.")
    def _edit_selected_structure(self):
        if not self.book:return
        kind,obj=self._selected_structure()
        if kind=="group" and obj:
            dlg=GroupDialog(obj,self)
            if not dlg.exec():return
            v=dlg.value(); before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write()
            if self.book.edit_group(obj,v["title"],v["id"]):self._history_commit("Editar grupo",before); self.reload_questbook(); self.statusBar().showMessage("Grupo atualizado.")
            else:QMessageBox.warning(self,"Falha","Não consegui editar o grupo. Verifique se o ID já existe.")
        elif kind=="chapter" and obj:
            dlg=ChapterDialog(self.book.chapter_groups,obj,self)
            if not dlg.exec():return
            v=dlg.value(); before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write()
            if self.book.edit_chapter(obj,v["title"],v["id"],v["group_id"],v["filename"]): self._history_commit("Editar capítulo",before); self.book.load(); self._populate_chapters(v["id"]); self.translations.set_book(self.book); self._reset_watcher(); self.statusBar().showMessage("Capítulo atualizado.")
            else:QMessageBox.warning(self,"Falha","Não consegui editar. O ID ou nome de arquivo pode já existir.")
    def _delete_selected_structure(self):
        if not self.book:return
        kind,obj=self._selected_structure()
        if kind=="group" and obj:
            ans=QMessageBox.question(self,"Excluir grupo",f'Excluir o grupo "{obj.title}"?\n\nOs capítulos NÃO serão apagados; ficarão sem grupo.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if ans!=QMessageBox.Yes:return
            before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write(); ok=self.book.delete_group(obj)
            if ok:self._history_commit("Excluir grupo",before)
        elif kind=="chapter" and obj:
            ans=QMessageBox.question(self,"Excluir capítulo",f'Excluir o capítulo "{obj.title}" e seu arquivo {obj.source_file.suffix}?\n\nIsso remove todas as quests do capítulo. Um backup será criado.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if ans!=QMessageBox.Yes:return
            before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write(); ok=self.book.delete_chapter(obj)
            if ok:self._history_commit("Excluir capítulo",before)
        else:return
        if ok:self.current_chapter=None; self.current_quest=None; self.reload_questbook()
        else:QMessageBox.warning(self,"Falha","Não consegui excluir o item selecionado.")

    # ---------- quest selection/editor ----------
    def _quest_display_title(self,q):
        if q.title:return q.title
        e=self.mods.items.get(q.primary_item_id or q.display_icon_item_id or q.icon_item_id); return e.display_name if e and e.display_name else "Quest sem título"
    def _quest_selected(self,quest):
        self.current_quest=quest; self.props.set_all_quests([q for c in self.book.chapters for q in c.quests] if self.book else []); self.props.set_quest(quest); self.right_tabs.setCurrentWidget(self.props);
        if self.auto_show_inspector and not self.right_panel.isVisible() and not (self._focus_mode_state is not None): self._set_panel_visible("right",True)
        self.statusBar().showMessage(f"Selecionada: {self._quest_display_title(quest)} • {quest.quest_id}")
    def _select_quest_in_book(self,q):
        if not self.book:return
        found=None
        def walk(item):
            nonlocal found
            if item.data(0,ROLE_KIND)=="chapter":
                ch=item.data(0,ROLE_OBJECT)
                if ch and ch.chapter_id==q.chapter_id: found=item; return
            for j in range(item.childCount()): walk(item.child(j))
        for i in range(self.chapter_tree.topLevelItemCount()): walk(self.chapter_tree.topLevelItem(i))
        if found:self.chapter_tree.setCurrentItem(found)
        node=self.canvas.nodes.get(q.quest_id)
        if node:node.setSelected(True); self.canvas.centerOn(node); self._quest_selected(q)
    def _goto_quest_id(self, quest_id: str):
        if not self.book or not quest_id:
            return
        q = self.book.quest_by_id.get(str(quest_id))
        if q is not None:
            self._select_quest_in_book(q)

    def _icon(self,item_id):
        raw=self.mods.get_texture_bytes(item_id)
        if not raw:return None
        p=QPixmap(); p.loadFromData(raw); return p
    def _shape_icon(self,shape_id):
        raw=self.mods.quest_shapes.get(shape_id)
        if not raw:return None
        p=QPixmap(); p.loadFromData(raw); return p
    def _draft_changed(self,title,item_id):
        if not self.current_quest:return
        node=self.canvas.nodes.get(self.current_quest.quest_id)
        if node:
            e=self.mods.items.get(item_id); node.set_display_title(title or (e.display_name if e else "") or "Quest sem título")
        self.statusBar().showMessage(f"Pré-validação: item não encontrado — {item_id}" if item_id and item_id not in self.mods.items else "Pré-validação: edição atual sem erro de item detectado")
    def _mark_own_write(self):self._ignore_external_until=time.monotonic()+1.25

    # ---------- global undo / redo ----------
    def _history_before(self):
        return self.history.snapshot(self.book.quest_root) if self.book else {}

    def _history_commit(self,label,before):
        if not self.book:return
        after=self.history.snapshot(self.book.quest_root)
        self.history.push(label,before,after); self._history_actions_changed()

    def _history_actions_changed(self):
        if hasattr(self,"undo_layout_action"):self.undo_layout_action.setEnabled(bool(self.book and self.history.can_undo))
        if hasattr(self,"redo_layout_action"):self.redo_layout_action.setEnabled(bool(self.book and self.history.can_redo))

    @staticmethod
    def _focused_text_editor(widget):
        if isinstance(widget,QComboBox) and widget.isEditable():return widget.lineEdit()
        return widget if isinstance(widget,(QLineEdit,QTextEdit,QPlainTextEdit)) else None

    def _undo_global(self):
        editor=self._focused_text_editor(self.focusWidget())
        if isinstance(editor,QLineEdit) and editor.isUndoAvailable():editor.undo(); return
        if isinstance(editor,(QTextEdit,QPlainTextEdit)) and editor.document().isUndoAvailable():editor.undo(); return
        if not self.book:return
        label=self.history.undo(self.book.quest_root)
        if not label:return
        self._mark_own_write(); self.canvas.clear_history(); self.reload_questbook(); self._history_actions_changed(); self.statusBar().showMessage(f"Desfeito: {label}")

    def _redo_global(self):
        editor=self._focused_text_editor(self.focusWidget())
        if isinstance(editor,QLineEdit) and editor.isRedoAvailable():editor.redo(); return
        if isinstance(editor,(QTextEdit,QPlainTextEdit)) and editor.document().isRedoAvailable():editor.redo(); return
        if not self.book:return
        label=self.history.redo(self.book.quest_root)
        if not label:return
        self._mark_own_write(); self.canvas.clear_history(); self.reload_questbook(); self._history_actions_changed(); self.statusBar().showMessage(f"Refeito: {label}")

    def _save_quest(self,values:dict):
        if not self.book or not self.current_quest:return
        before=self._history_before(); q=self.current_quest; backup_questbook(self.book.quest_root); self._mark_own_write(); ok=True
        self.book.save_title(q,values.get("title","")); self.book.save_description(q,values.get("description",""))
        task_specs=[dict(x) for x in values.get("tasks",[])]; main_item=values.get("item_id",""); old_item=q.primary_item_id
        if main_item and main_item!=old_item and not values.get("tasks_dirty"):ok=self.book.replace_first_item_task(q,main_item) and ok
        for spec in task_specs:
            if spec.get("type")=="item":spec["item_id"]=main_item or spec.get("item_id",""); break
        ok=self.book.save_properties(q,values) and ok; ok=self.book.set_dependencies(q,values.get("dependencies",[])) and ok
        if values.get("tasks_dirty"):ok=self.book.set_tasks(q,task_specs) and ok
        if values.get("rewards_dirty"):ok=self.book.set_rewards(q,values.get("rewards",[])) and ok
        self._history_commit("Editar quest",before); self._select_after_reload=q.quest_id; self.reload_questbook(); self.statusBar().showMessage("Quest salva e validada." if ok else "Quest salva parcialmente; confira Problemas.")
    def _canvas_selection_changed(self,quests):
        n=len(quests); self.selection_label.setText(f"{n} selecionada" if n==1 else f"{n} selecionadas")
        if hasattr(self,"quest_single_actions"):
            for a in self.quest_single_actions: a.setEnabled(n==1)
            self.dependencies_action.setEnabled(n>=1)
            self.delete_action.setEnabled(n>=1)
        enabled=n>=2
        for a in self.layout_actions:
            # Undo/redo are managed by global history; batch/layout tools need 2+.
            if a not in (getattr(self,"undo_layout_action",None),getattr(self,"redo_layout_action",None)): a.setEnabled(enabled)
        self.gap_x.setEnabled(enabled); self.gap_y.setEnabled(enabled); self.gap_x_btn.setEnabled(enabled); self.gap_y_btn.setEnabled(enabled)
        if hasattr(self,"layout_tb") and self.contextual_layout:
            self.layout_tb.setVisible(enabled and self.main_tabs.currentIndex()==0 and self._focus_mode_state is None)
        if n==1 and quests[0] is not self.current_quest:self._quest_selected(quests[0])
        elif n>=2:
            self.statusBar().showMessage(f"Edição em lote: {n} quests selecionadas • layout e dependências serão aplicados ao conjunto")

    def _batch_dependencies(self, quests=None):
        if not self.book:
            return
        selected = list(quests or self.canvas.selected_quests())
        unique = []
        seen = set()
        for q in selected:
            if q and q.quest_id not in seen:
                seen.add(q.quest_id)
                unique.append(q)
        if len(unique) < 2:
            return QMessageBox.information(
                self,
                "Dependências em lote",
                "Selecione duas ou mais quests primeiro.\n\n"
                "Ctrl+clique adiciona quests à seleção; Ctrl+Shift+arrastar faz seleção por área.",
            )
        dlg = BatchDependenciesDialog(
            unique,
            list(self.book.quest_by_id.values()),
            self._quest_display_title,
            self,
        )
        if not dlg.exec():
            return
        targets = dlg.target_ids()
        mode = dlg.mode()
        if not targets:
            return
        target_names = [
            self._quest_display_title(self.book.quest_by_id[t])
            for t in targets
            if t in self.book.quest_by_id
        ]
        verb = "Adicionar" if mode == "add" else "Remover"
        detail = "\n".join(f"• {name}" for name in target_names[:8])
        if len(target_names) > 8:
            detail += f"\n• ... e mais {len(target_names) - 8}"
        ans = QMessageBox.question(
            self,
            "Confirmar edição em lote",
            f"{verb} {len(targets)} dependência(s) em {len(unique)} quests selecionadas?\n\n"
            f"{detail}\n\n"
            "A operação inteira poderá ser desfeita com Ctrl+Z.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ans != QMessageBox.Yes:
            return
        before = self._history_before()
        backup_questbook(self.book.quest_root)
        self._mark_own_write()
        ok, changed = self.book.batch_update_dependencies(unique, targets, mode)
        if not changed:
            return self.statusBar().showMessage("Nenhuma dependência precisou ser alterada.")
        label = ("Adicionar" if mode == "add" else "Remover") + f" dependências em {changed} quests"
        self._history_commit(label, before)
        selected_ids = [q.quest_id for q in unique]
        self.reload_questbook()
        self._restore_multi_selection(selected_ids)
        self._history_actions_changed()
        self.statusBar().showMessage(
            f"{label} • Ctrl+Z desfaz tudo"
            if ok
            else f"{label}, com falhas parciais; confira Problemas"
        )

    def _restore_multi_selection(self, quest_ids):
        wanted = set(quest_ids or [])
        if not wanted:
            return

        def apply():
            for qid, node in self.canvas.nodes.items():
                node.setSelected(qid in wanted)

        QTimer.singleShot(0, apply)

    def _quests_moved(self,changes,label="Mover quests"):
        if not self.book or not changes:return
        actual=[(q,x,y) for q,x,y in changes if abs(q.x-x)>=.001 or abs(q.y-y)>=.001]
        if not actual:return
        before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write()
        if self.book.save_positions(actual):
            self._history_commit(label,before); self.statusBar().showMessage(f"{label} • {len(actual)} posição(ões) salvas")
        else:QMessageBox.warning(self,"Posições não salvas","Não consegui localizar uma ou mais quests no arquivo do capítulo.")
    def _new_quest_center(self):
        if not self.current_chapter:return QMessageBox.information(self,"Nova Quest","Abra um capítulo primeiro.")
        p=self.canvas.mapToScene(self.canvas.viewport().rect().center()); self._new_quest_at(p.x()/self.canvas.SCALE,p.y()/self.canvas.SCALE)
    def _new_quest_at(self,x,y):
        if not self.book or not self.current_chapter:return
        dlg=NewQuestDialog(self.mods,x,y,self)
        if not dlg.exec():return
        v=dlg.value(); before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write(); qid=self.book.create_quest(self.current_chapter,**v)
        if qid:self._history_commit("Criar quest",before); self._select_after_reload=qid; self.reload_questbook(); self.statusBar().showMessage("Nova quest criada.")
        else:QMessageBox.warning(self,"Falha","Não consegui inserir a nova quest no capítulo.")
    def _duplicate_current(self):
        if self.current_quest:self._duplicate_quest(self.current_quest)
    def _duplicate_quest(self,quest):
        if not self.book:return
        before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write(); qid=self.book.duplicate_quest(quest)
        if qid:self._history_commit("Duplicar quest",before); self._select_after_reload=qid; self.reload_questbook(); self.statusBar().showMessage("Quest duplicada.")
        else:QMessageBox.warning(self,"Falha","Não consegui duplicar a quest com segurança.")
    def _delete_current(self):
        selected=self.canvas.selected_quests() if hasattr(self,"canvas") else []
        if len(selected)>1:self._delete_many_quests(selected)
        elif selected:self._delete_quest(selected[0])
        elif self.current_quest:self._delete_quest(self.current_quest)
    def _delete_quest(self,quest):
        if not self.book:return
        title=self._quest_display_title(quest); answer=QMessageBox.question(self,"Excluir quest",f'Excluir "{title}"?\n\nID: {quest.quest_id}\n\nUm backup será criado.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return
        before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write()
        if self.book.delete_quest(quest):self._history_commit("Excluir quest",before); self.current_quest=None; self.reload_questbook(); self.statusBar().showMessage(f"Quest excluída: {title}")
        else:QMessageBox.warning(self,"Não foi possível excluir","A quest não foi localizada com segurança.")
    def _delete_many_quests(self,quests):
        if not self.book or not quests:return
        unique=[]; seen=set()
        for q in quests:
            if q.quest_id not in seen: seen.add(q.quest_id); unique.append(q)
        answer=QMessageBox.question(self,"Excluir quests",f"Excluir {len(unique)} quests selecionadas?\n\nAs dependências que apontam para elas também serão limpas. Um único backup será criado.",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return
        before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write(); ok=True
        for q in unique: ok=self.book.delete_quest(q) and ok
        self._history_commit(f"Excluir {len(unique)} quests",before); self.current_quest=None; self.reload_questbook(); self.statusBar().showMessage(f"{len(unique)} quests excluídas." if ok else "Exclusão concluída com falhas; confira o Quest Book.")
    def _show_properties(self,quest):
        self._quest_selected(quest); self.main_tabs.setCurrentIndex(0); self.right_tabs.setCurrentWidget(self.props); self.props.focus_general(); self.props.raise_(); self.props.activateWindow(); self.statusBar().showMessage(f"Propriedades abertas: {self._quest_display_title(quest)}")
    def _show_current_properties(self):
        if self.current_quest:
            self._show_properties(self.current_quest)

    def _open_quest_editor_tab(self, index):
        if not self.current_quest:
            return
        self._show_properties(self.current_quest)
        self.props.tabs.setCurrentIndex(index)

    def _open_dependencies_editor(self):
        selected=self.canvas.selected_quests() if hasattr(self,"canvas") else []
        if len(selected)>=2:
            return self._batch_dependencies(selected)
        if self.current_quest:
            self._open_quest_editor_tab(1)

    def _copy_current_id(self):
        if not self.current_quest:
            return
        QApplication.clipboard().setText(self.current_quest.quest_id)
        self.statusBar().showMessage(f"ID copiado: {self.current_quest.quest_id}")

    def _save_current_quest(self):
        if self.current_quest:
            self.props._save()

    def _focus_title(self):
        if self.current_quest:self._show_properties(self.current_quest); self.props.focus_title()
    def _focus_description(self):
        if self.current_quest:self._show_properties(self.current_quest); self.props.focus_description()

    def _save_translations(self,rows):
        if not self.book:return
        changed=[(k,p,e) for k,p,e in rows if p!=self.book.lang_pt.get(k,"") or e!=self.book.lang_en.get(k,"")]
        if not changed:return self.statusBar().showMessage("Nenhuma tradução alterada.")
        before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write()
        for key,pt,en in changed:self.book.save_translation(key,pt,en)
        self._history_commit(f"Editar {len(changed)} tradução(ões)",before); self.reload_questbook(); self.main_tabs.setCurrentWidget(self.translations); self.statusBar().showMessage(f"{len(changed)} tradução(ões) salva(s).")
    def _import_translations(self, records):
        if not self.book or not records:return
        changed=[]; skipped=0
        for row in records:
            key=str(row.get("key","")).strip()
            if not key.startswith(("quest.","task.","reward.","quest_link.","image.","chapter.","chapter_group.","file.","reward_table.")):
                skipped+=1; continue
            old_pt=self.book.lang_pt.get(key,""); old_en=self.book.lang_en.get(key,"")
            # Import is merge-safe: blank cells never erase an existing translation.
            raw_pt=str(row.get("pt_br","")).replace("\r\n","\n").replace("\r","\n")
            raw_en=str(row.get("en_us","")).replace("\r\n","\n").replace("\r","\n")
            pt=raw_pt if raw_pt.strip() else old_pt
            en=raw_en if raw_en.strip() else old_en
            if pt!=old_pt or en!=old_en:changed.append((key,pt,en))
        if not changed:
            return QMessageBox.information(self,"Importar traduções",f"Nenhuma alteração nova encontrada. {skipped} linha(s) inválida(s) ignorada(s)." if skipped else "Nenhuma alteração nova encontrada.")
        ans=QMessageBox.question(self,"Importar traduções",f"Aplicar {len(changed)} alteração(ões) de tradução?\n\nCélulas vazias NÃO apagam textos existentes.\nCtrl+Z poderá desfazer a importação inteira.",QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)
        if ans!=QMessageBox.Yes:return
        before=self._history_before(); backup_questbook(self.book.quest_root); self._mark_own_write()
        for key,pt,en in changed:self.book.save_translation(key,pt,en)
        self._history_commit(f"Importar {len(changed)} tradução(ões)",before); self.reload_questbook(); self.main_tabs.setCurrentWidget(self.translations); self._history_actions_changed(); self.statusBar().showMessage(f"{len(changed)} tradução(ões) importada(s). Ctrl+Z desfaz a importação.")

    def _validate(self):
        if not self.book:return
        probs=validate(self.book,self.mods); self.problems.set_problems(probs); e=sum(p.severity=="error" for p in probs); w=sum(p.severity=="warning" for p in probs); info=sum(p.severity=="info" for p in probs); self.statusBar().showMessage(f"Validação: {e} erro(s) • {w} aviso(s) • {info} informação(ões)")
    def _goto_problem(self,problem):
        if not self.book or not problem.quest_id:return
        q=self.book.quest_by_id.get(problem.quest_id)
        if q:self.main_tabs.setCurrentIndex(0); self._select_quest_in_book(q)
    def _reset_watcher(self):
        paths=self.file_watcher.files()+self.file_watcher.directories()
        if paths:self.file_watcher.removePaths(paths)
        if not self.book:return
        root=self.book.quest_root
        dirs=[root]
        for base_name in ("chapters","lang","reward_tables"):
            base=root/base_name
            if base.exists():
                dirs.extend(p for p in base.rglob("*") if p.is_dir())
                dirs.append(base)
        # Deduplicate while preserving order. Watching split lang directories is important
        # for both Lang Splitter (SNBT) and native 26.1.2 JSON5 translation files.
        seen=set(); dir_paths=[]
        for p in dirs:
            sp=str(p)
            if p.exists() and sp not in seen:seen.add(sp);dir_paths.append(sp)
        if dir_paths:self.file_watcher.addPaths(dir_paths)
        files=[]
        for pattern in ("*.snbt","*.json5"):
            files.extend(str(p) for p in root.rglob(pattern) if p.is_file())
        if files:self.file_watcher.addPaths(list(dict.fromkeys(files)))
    def _external_change(self,path):
        if time.monotonic()<self._ignore_external_until:return
        self.statusBar().showMessage(f"Alteração externa detectada: {Path(path).name}. Recarregando..."); self.reload_timer.start(450)
