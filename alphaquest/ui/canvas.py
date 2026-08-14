from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsView, QMenu

from ..core.models import QuestInfo


class QuestNode(QGraphicsObject):
    """Visual node for one quest.

    A node deliberately keeps its position in scene pixels; QuestCanvas converts to/from
    FTB Quests x/y units.  This avoids leaking editor zoom into the stored quest layout.
    """

    selectedQuest = Signal(object)
    positionChanged = Signal()
    dragCommitted = Signal(object)

    def __init__(self, quest: QuestInfo, pixmap: QPixmap | None = None, display_title: str = "", shape_pixmap: QPixmap | None = None):
        super().__init__()
        self.quest = quest
        self.pixmap = pixmap
        self.shape_pixmap = shape_pixmap
        self.display_title = display_title or quest.title or "Quest sem título"
        self.snap_enabled = False
        self.snap_step_px = 0.0
        self._suspend_snap = False
        self._drag_before: dict[str, tuple[float, float]] = {}
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
            | QGraphicsItem.ItemIsFocusable
        )
        self.setCursor(Qt.OpenHandCursor)
        self._refresh_tooltip()
        scale = max(.35, min(3.0, quest.size or 1.0))
        self.setScale(scale)

    def _refresh_tooltip(self):
        self.setToolTip(
            f"{self.display_title}\n{self.quest.quest_id}\n{self.quest.primary_item_id}\n"
            f"Shape: {self.quest.shape or 'padrão'}"
        )

    def set_display_title(self, title):
        self.display_title = title or "Quest sem título"
        self._refresh_tooltip()
        self.update()

    def set_snap(self, enabled: bool, step_px: float):
        self.snap_enabled = bool(enabled)
        self.snap_step_px = max(0.0, float(step_px))

    def set_pos_without_snap(self, pos: QPointF):
        old = self._suspend_snap
        self._suspend_snap = True
        try:
            self.setPos(pos)
        finally:
            self._suspend_snap = old

    def boundingRect(self):
        return QRectF(-82, -43, 164, 116)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        selected = self.isSelected()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawRoundedRect(QRectF(-30, -30, 60, 60).translated(2, 4), 12, 12)
        if self.shape_pixmap and not self.shape_pixmap.isNull():
            painter.drawPixmap(QRectF(-34, -34, 68, 68).toRect(), self.shape_pixmap)
            if selected:
                painter.setPen(QPen(QColor("#5eead4"), 3))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QRectF(-35, -35, 70, 70))
        else:
            painter.setPen(QPen(QColor("#5eead4") if selected else QColor("#52616b"), 3 if selected else 2))
            painter.setBrush(QColor("#202b31"))
            painter.drawRoundedRect(QRectF(-30, -30, 60, 60), 12, 12)
        if self.pixmap and not self.pixmap.isNull():
            painter.drawPixmap(QRectF(-22, -22, 44, 44).toRect(), self.pixmap)
        else:
            painter.setPen(QColor("#91a4ae"))
            painter.drawText(QRectF(-20, -20, 40, 40), Qt.AlignCenter, "?")
        label = QRectF(-78, 38, 156, 34)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#11191d"))
        painter.drawRoundedRect(label, 7, 7)
        painter.setPen(QColor("#f4f7f8"))
        font = painter.font()
        font.setPointSizeF(8.5)
        font.setBold(selected)
        painter.setFont(font)
        painter.drawText(
            label.adjusted(5, 3, -5, -3),
            Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap,
            self.display_title[:72],
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.snap_enabled and not self._suspend_snap and self.snap_step_px > 0:
            p = QPointF(value)
            step = self.snap_step_px
            value = QPointF(round(p.x() / step) * step, round(p.y() / step) * step)
        result = super().itemChange(change, value)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.positionChanged.emit()
        return result

    def mousePressEvent(self, event):
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)
        # Capture AFTER Qt has applied Ctrl selection semantics, so a drag of one
        # selected node records the whole selected group.
        self._drag_before = {}
        if self.scene():
            for item in self.scene().selectedItems():
                if isinstance(item, QuestNode):
                    p = item.pos()
                    self._drag_before[item.quest.quest_id] = (p.x(), p.y())
        self.selectedQuest.emit(self.quest)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.OpenHandCursor)
        self.dragCommitted.emit(dict(self._drag_before))
        self._drag_before = {}


class QuestCanvas(QGraphicsView):
    questSelected = Signal(object)
    positionsCommitted = Signal(object, str)  # [(QuestInfo, x_ftb, y_ftb)], label
    deleteRequested = Signal(object)
    deleteManyRequested = Signal(object)
    duplicateRequested = Signal(object)
    newQuestRequested = Signal(float, float)
    propertiesRequested = Signal(object)
    editTitleRequested = Signal(object)
    editDescriptionRequested = Signal(object)
    dependenciesRequested = Signal(object)
    tasksRequested = Signal(object)
    rewardsRequested = Signal(object)
    copyIdRequested = Signal(object)
    selectionChanged = Signal(object)
    historyChanged = Signal(bool, bool)
    selectionToolChanged = Signal(bool)
    batchDependenciesRequested = Signal(object)

    SCALE = 110.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.scene_.selectionChanged.connect(self._scene_selection_changed)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setRubberBandSelectionMode(Qt.IntersectsItemShape)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#0c1215"))
        self.nodes: dict[str, QuestNode] = {}
        self.edge_items = []
        self.current_chapter = None
        self.setSceneRect(-8000, -8000, 16000, 16000)
        self.setFocusPolicy(Qt.StrongFocus)
        self._rubber_active = False
        self._selection_tool_active = False
        self._space_pan = False
        self.snap_enabled = False
        self.snap_step = 0.5  # FTB units
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []

    # ---------- navigation / selection ----------
    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        nxt = self.transform().m11() * factor
        if .2 <= nxt <= 4.5:
            self.scale(factor, factor)

    def set_selection_tool(self, enabled: bool):
        """Enable a persistent rubber-band selection tool.

        Ctrl+Shift+drag remains available as a temporary shortcut. The visible
        toolbar toggle exists because modifier-only gestures are easy to forget.
        """
        enabled = bool(enabled)
        if self._selection_tool_active == enabled:
            return
        self._selection_tool_active = enabled
        if not self._rubber_active and not self._space_pan:
            self.setDragMode(QGraphicsView.RubberBandDrag if enabled else QGraphicsView.ScrollHandDrag)
        self.selectionToolChanged.emit(enabled)

    def mousePressEvent(self, event):
        # Ctrl+Shift+drag on empty canvas is a temporary area-selection gesture.
        both = (event.modifiers() & Qt.ControlModifier) and (event.modifiers() & Qt.ShiftModifier)
        empty = not isinstance(self.itemAt(event.pos()), QuestNode)
        if event.button() == Qt.LeftButton and both and empty:
            self._rubber_active = True
            self.setDragMode(QGraphicsView.RubberBandDrag)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._rubber_active:
            self._rubber_active = False
            if not self._space_pan:
                self.setDragMode(QGraphicsView.RubberBandDrag if self._selection_tool_active else QGraphicsView.ScrollHandDrag)

    def keyPressEvent(self, event: QKeyEvent):
        selected = self.selected_nodes()
        if event.matches(QKeySequence.SelectAll):
            self.select_all_quests(); event.accept(); return
        if event.key() == Qt.Key_Escape:
            self.clear_quest_selection(); event.accept(); return
        if event.key() == Qt.Key_S and event.modifiers() == Qt.NoModifier:
            self.set_selection_tool(not self._selection_tool_active); event.accept(); return
        if event.key() == Qt.Key_Space and not self._space_pan:
            self._space_pan = True
            self.setDragMode(QGraphicsView.ScrollHandDrag); event.accept(); return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and selected:
            if len(selected) == 1:
                self.deleteRequested.emit(selected[0].quest)
            else:
                self.deleteManyRequested.emit([n.quest for n in selected])
            event.accept(); return
        if event.key() == Qt.Key_T and len(selected) == 1 and event.modifiers() == Qt.NoModifier:
            self.editTitleRequested.emit(selected[0].quest); event.accept(); return
        if event.key() == Qt.Key_D and len(selected) == 1 and event.modifiers() == Qt.NoModifier:
            self.editDescriptionRequested.emit(selected[0].quest); event.accept(); return
        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down) and selected:
            base = self.snap_step if self.snap_enabled else 0.5
            if event.modifiers() & Qt.ShiftModifier:
                base *= 5.0
            dx = (-base if event.key() == Qt.Key_Left else base if event.key() == Qt.Key_Right else 0.0)
            dy = (-base if event.key() == Qt.Key_Up else base if event.key() == Qt.Key_Down else 0.0)
            self.move_selection_by(dx, dy, f"Mover {len(selected)} quest(s)")
            event.accept(); return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Space and self._space_pan:
            self._space_pan = False
            if not self._rubber_active:
                self.setDragMode(QGraphicsView.RubberBandDrag if self._selection_tool_active else QGraphicsView.ScrollHandDrag)
            event.accept(); return
        super().keyReleaseEvent(event)

    def selected_nodes(self) -> list[QuestNode]:
        return [x for x in self.scene_.selectedItems() if isinstance(x, QuestNode)]

    def selected_quests(self) -> list[QuestInfo]:
        return [n.quest for n in self.selected_nodes()]

    def selected_quest(self):
        selected = self.selected_nodes()
        return selected[0].quest if selected else None

    def _scene_selection_changed(self):
        self.selectionChanged.emit(self.selected_quests())
        self.viewport().update()

    def select_all_quests(self):
        for node in self.nodes.values():
            node.setSelected(True)

    def clear_quest_selection(self):
        self.scene_.clearSelection()

    # ---------- context menu ----------
    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        node = item if isinstance(item, QuestNode) else None
        if node:
            if not node.isSelected():
                self.scene_.clearSelection()
                node.setSelected(True)
            self.questSelected.emit(node.quest)
        menu = QMenu(self)
        selected = self.selected_nodes()
        if node:
            if len(selected) > 1:
                menu.addAction(f"Selecionadas: {len(selected)} quests").setEnabled(False)
                menu.addSeparator()
                deps = menu.addAction("⛓ Dependências em lote...")
                deps.triggered.connect(lambda: self.batchDependenciesRequested.emit([n.quest for n in self.selected_nodes()]))
                menu.addSeparator()
                a = menu.addAction("↤ Alinhar à esquerda"); a.triggered.connect(lambda: self.align_selection("left"))
                a = menu.addAction("↔ Centralizar X"); a.triggered.connect(lambda: self.align_selection("hcenter"))
                a = menu.addAction("↥ Alinhar ao topo"); a.triggered.connect(lambda: self.align_selection("top"))
                a = menu.addAction("↕ Centralizar Y"); a.triggered.connect(lambda: self.align_selection("vcenter"))
                menu.addSeparator()
                x = menu.addAction(f"Excluir {len(selected)} quests   Delete"); x.triggered.connect(lambda: self.deleteManyRequested.emit([n.quest for n in self.selected_nodes()]))
            else:
                a = menu.addAction("✦ Propriedades da quest   Ctrl+E"); a.triggered.connect(lambda: self.propertiesRequested.emit(node.quest))
                a = menu.addAction("✎ Editar título   F2"); a.triggered.connect(lambda: self.editTitleRequested.emit(node.quest))
                a = menu.addAction("☰ Editar descrição"); a.triggered.connect(lambda: self.editDescriptionRequested.emit(node.quest))
                menu.addSeparator()
                a = menu.addAction("⛓ Dependências"); a.triggered.connect(lambda: self.dependenciesRequested.emit(node.quest))
                a = menu.addAction("✓ Tasks"); a.triggered.connect(lambda: self.tasksRequested.emit(node.quest))
                a = menu.addAction("★ Rewards"); a.triggered.connect(lambda: self.rewardsRequested.emit(node.quest))
                menu.addSeparator()
                d = menu.addAction("⧉ Duplicar quest   Ctrl+D"); d.triggered.connect(lambda: self.duplicateRequested.emit(node.quest))
                c = menu.addAction("⧉ Copiar ID"); c.triggered.connect(lambda: self.copyIdRequested.emit(node.quest))
                menu.addSeparator()
                x = menu.addAction("Excluir quest   Delete"); x.triggered.connect(lambda: self.deleteRequested.emit(node.quest))
        else:
            scene_pos = self.mapToScene(event.pos())
            n = menu.addAction("＋ Nova Quest   Ctrl+N"); n.triggered.connect(lambda: self.newQuestRequested.emit(scene_pos.x() / self.SCALE, scene_pos.y() / self.SCALE))
            if len(selected) > 1:
                menu.addSeparator()
                deps = menu.addAction("⛓ Dependências em lote...")
                deps.triggered.connect(lambda: self.batchDependenciesRequested.emit([n.quest for n in self.selected_nodes()]))
                a = menu.addAction("◎ Juntar seleção no centro"); a.triggered.connect(self.stack_selection_center)
        menu.exec(event.globalPos())

    # ---------- loading ----------
    def load_chapter(self, chapter, icon_provider, title_provider=None, shape_provider=None, preserve_view=False):
        old_id = self.current_chapter.chapter_id if self.current_chapter else None
        old_transform = self.transform()
        old_center = self.mapToScene(self.viewport().rect().center())
        self.scene_.clear()
        self.nodes.clear()
        self.edge_items.clear()
        self.current_chapter = chapter
        if old_id != chapter.chapter_id:
            self.clear_history()
        for q in chapter.quests:
            title = title_provider(q) if title_provider else (q.title or "Quest sem título")
            shape = shape_provider(q.shape) if shape_provider and q.shape else None
            node = QuestNode(q, icon_provider(q.primary_item_id or q.icon_item_id), title, shape)
            node.set_snap(self.snap_enabled, self.snap_step * self.SCALE)
            node.setPos(QPointF(q.x * self.SCALE, q.y * self.SCALE))
            node.selectedQuest.connect(self.questSelected)
            node.positionChanged.connect(self._redraw_edges)
            node.dragCommitted.connect(self._drag_committed)
            self.scene_.addItem(node)
            self.nodes[q.quest_id] = node
        self._redraw_edges()
        if preserve_view:
            self.setTransform(old_transform)
            self.centerOn(old_center)
        elif chapter.quests:
            bounds = self.scene_.itemsBoundingRect().adjusted(-120, -120, 120, 120)
            self.fitInView(bounds, Qt.KeepAspectRatio)
            if self.transform().m11() < .42:
                self.resetTransform(); self.scale(.42, .42); self.centerOn(bounds.center())

    # ---------- snapping ----------
    def set_snap(self, enabled: bool, step: float | None = None):
        self.snap_enabled = bool(enabled)
        if step is not None:
            self.snap_step = max(0.05, float(step))
        for node in self.nodes.values():
            node.set_snap(self.snap_enabled, self.snap_step * self.SCALE)

    # ---------- position transactions / history ----------
    def _capture_positions(self, nodes: list[QuestNode] | None = None) -> dict[str, tuple[float, float]]:
        nodes = nodes if nodes is not None else self.selected_nodes()
        return {n.quest.quest_id: (n.pos().x() / self.SCALE, n.pos().y() / self.SCALE) for n in nodes}

    def _drag_committed(self, before_px: dict[str, tuple[float, float]]):
        if not before_px:
            return
        before = {qid: (px / self.SCALE, py / self.SCALE) for qid, (px, py) in before_px.items()}
        nodes = [self.nodes[qid] for qid in before if qid in self.nodes]
        after = self._capture_positions(nodes)
        self._commit_position_transaction(before, after, f"Mover {len(after)} quest(s)")

    @staticmethod
    def _different(before: dict, after: dict) -> bool:
        if before.keys() != after.keys():
            return True
        return any(abs(before[k][0] - after[k][0]) > 1e-6 or abs(before[k][1] - after[k][1]) > 1e-6 for k in before)

    def _commit_position_transaction(self, before: dict[str, tuple[float, float]], after: dict[str, tuple[float, float]], label: str, record=True):
        if not self._different(before, after):
            return
        if record:
            self._undo_stack.append({"label": label, "before": dict(before), "after": dict(after)})
            if len(self._undo_stack) > 100:
                self._undo_stack.pop(0)
            self._redo_stack.clear()
            self.historyChanged.emit(bool(self._undo_stack), bool(self._redo_stack))
        payload = []
        for qid, (x, y) in after.items():
            node = self.nodes.get(qid)
            if node:
                payload.append((node.quest, x, y))
        if payload:
            self.positionsCommitted.emit(payload, label)

    def _apply_snapshot(self, snap: dict[str, tuple[float, float]]):
        for qid, (x, y) in snap.items():
            node = self.nodes.get(qid)
            if node:
                node.set_pos_without_snap(QPointF(x * self.SCALE, y * self.SCALE))
        self._redraw_edges()

    def undo_layout(self):
        if not self._undo_stack:
            return
        cmd = self._undo_stack.pop()
        self._apply_snapshot(cmd["before"])
        self._redo_stack.append(cmd)
        self.historyChanged.emit(bool(self._undo_stack), bool(self._redo_stack))
        self._commit_position_transaction(cmd["after"], cmd["before"], "Desfazer: " + cmd["label"], record=False)

    def redo_layout(self):
        if not self._redo_stack:
            return
        cmd = self._redo_stack.pop()
        self._apply_snapshot(cmd["after"])
        self._undo_stack.append(cmd)
        self.historyChanged.emit(bool(self._undo_stack), bool(self._redo_stack))
        self._commit_position_transaction(cmd["before"], cmd["after"], "Refazer: " + cmd["label"], record=False)

    def clear_history(self):
        self._undo_stack.clear(); self._redo_stack.clear()
        self.historyChanged.emit(False, False)

    # ---------- layout commands ----------
    def _layout_transaction(self, label: str, fn):
        nodes = self.selected_nodes()
        if len(nodes) < 2:
            return
        before = self._capture_positions(nodes)
        fn(nodes)
        after = self._capture_positions(nodes)
        self._redraw_edges()
        self._commit_position_transaction(before, after, label)

    def align_selection(self, mode: str):
        labels = {
            "left": "Alinhar à esquerda", "hcenter": "Centralizar horizontalmente", "right": "Alinhar à direita",
            "top": "Alinhar ao topo", "vcenter": "Centralizar verticalmente", "bottom": "Alinhar à base",
        }
        def apply(nodes):
            rects = [n.sceneBoundingRect() for n in nodes]
            union = rects[0]
            for r in rects[1:]: union = union.united(r)
            for n in nodes:
                r = n.sceneBoundingRect(); p = n.pos(); dx = dy = 0.0
                if mode == "left": dx = union.left() - r.left()
                elif mode == "hcenter": dx = union.center().x() - r.center().x()
                elif mode == "right": dx = union.right() - r.right()
                elif mode == "top": dy = union.top() - r.top()
                elif mode == "vcenter": dy = union.center().y() - r.center().y()
                elif mode == "bottom": dy = union.bottom() - r.bottom()
                n.set_pos_without_snap(QPointF(p.x() + dx, p.y() + dy))
        self._layout_transaction(labels.get(mode, "Alinhar seleção"), apply)

    def distribute_selection(self, axis: str):
        nodes = self.selected_nodes()
        if len(nodes) < 3:
            return
        before = self._capture_positions(nodes)
        if axis == "x":
            ordered = sorted(nodes, key=lambda n: n.sceneBoundingRect().center().x())
            a, b = ordered[0].sceneBoundingRect().center().x(), ordered[-1].sceneBoundingRect().center().x()
            step = (b - a) / (len(ordered) - 1)
            for i, n in enumerate(ordered[1:-1], 1):
                r = n.sceneBoundingRect(); p = n.pos(); dx = (a + step * i) - r.center().x(); n.set_pos_without_snap(QPointF(p.x() + dx, p.y()))
            label = "Distribuir horizontalmente"
        else:
            ordered = sorted(nodes, key=lambda n: n.sceneBoundingRect().center().y())
            a, b = ordered[0].sceneBoundingRect().center().y(), ordered[-1].sceneBoundingRect().center().y()
            step = (b - a) / (len(ordered) - 1)
            for i, n in enumerate(ordered[1:-1], 1):
                r = n.sceneBoundingRect(); p = n.pos(); dy = (a + step * i) - r.center().y(); n.set_pos_without_snap(QPointF(p.x(), p.y() + dy))
            label = "Distribuir verticalmente"
        after = self._capture_positions(nodes); self._redraw_edges(); self._commit_position_transaction(before, after, label)

    def space_selection(self, axis: str, gap_ftb: float):
        gap_px = max(0.0, float(gap_ftb)) * self.SCALE
        nodes = self.selected_nodes()
        if len(nodes) < 2:
            return
        before = self._capture_positions(nodes)
        if axis == "x":
            ordered = sorted(nodes, key=lambda n: n.sceneBoundingRect().left())
            cursor = ordered[0].sceneBoundingRect().right()
            for n in ordered[1:]:
                r = n.sceneBoundingRect(); p = n.pos(); dx = (cursor + gap_px) - r.left(); n.set_pos_without_snap(QPointF(p.x() + dx, p.y())); cursor = n.sceneBoundingRect().right()
            label = f"Espaçar horizontalmente ({gap_ftb:g} u)"
        else:
            ordered = sorted(nodes, key=lambda n: n.sceneBoundingRect().top())
            cursor = ordered[0].sceneBoundingRect().bottom()
            for n in ordered[1:]:
                r = n.sceneBoundingRect(); p = n.pos(); dy = (cursor + gap_px) - r.top(); n.set_pos_without_snap(QPointF(p.x(), p.y() + dy)); cursor = n.sceneBoundingRect().bottom()
            label = f"Espaçar verticalmente ({gap_ftb:g} u)"
        after = self._capture_positions(nodes); self._redraw_edges(); self._commit_position_transaction(before, after, label)

    def stack_selection_center(self):
        def apply(nodes):
            rects = [n.sceneBoundingRect() for n in nodes]
            union = rects[0]
            for r in rects[1:]: union = union.united(r)
            target = union.center()
            for n in nodes:
                r = n.sceneBoundingRect(); p = n.pos(); delta = target - r.center(); n.set_pos_without_snap(p + delta)
        self._layout_transaction("Juntar seleção no centro", apply)

    def move_selection_by(self, dx_ftb: float, dy_ftb: float, label="Mover seleção"):
        nodes = self.selected_nodes()
        if not nodes:
            return
        before = self._capture_positions(nodes)
        dx, dy = dx_ftb * self.SCALE, dy_ftb * self.SCALE
        for n in nodes:
            p = n.pos(); n.set_pos_without_snap(QPointF(p.x() + dx, p.y() + dy))
        after = self._capture_positions(nodes); self._redraw_edges(); self._commit_position_transaction(before, after, label)

    # ---------- dependency lines ----------
    def _redraw_edges(self):
        for item in self.edge_items:
            try:
                self.scene_.removeItem(item)
            except RuntimeError:
                pass
        self.edge_items.clear()
        if not self.current_chapter:
            return
        for q in self.current_chapter.quests:
            dst = self.nodes.get(q.quest_id)
            if not dst:
                continue
            for dep in q.dependencies:
                src = self.nodes.get(dep)
                if not src:
                    continue
                p1, p2 = src.pos(), dst.pos()
                path = QPainterPath(p1)
                dx = max(45.0, abs(p2.x() - p1.x()) * .45)
                path.cubicTo(QPointF(p1.x() + dx, p1.y()), QPointF(p2.x() - dx, p2.y()), p2)
                item = self.scene_.addPath(path, QPen(QColor("#40515b"), 2.2))
                item.setZValue(-10)
                self.edge_items.append(item)
