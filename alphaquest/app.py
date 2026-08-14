from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Alpha Quest Editor")
    app.setOrganizationName("Alpha Devs")
    app.setStyleSheet(r'''
        * { font-family: "Segoe UI"; font-size: 10pt; }
        QMainWindow, QWidget { background: #11181c; color: #e8eef1; }
        QMenu { background: #10181c; color: #e8eef1; border: 1px solid #30434c; padding: 5px; }
        QMenu::item { padding: 7px 24px 7px 10px; border-radius: 5px; }
        QMenu::item:selected { background: #1d3a3e; }
        QToolBar { background: #0b1114; border: 0; border-bottom: 1px solid #25343c; spacing: 8px; padding: 6px; }
        QToolBar QToolButton { background: #18242a; border: 1px solid #2d424c; border-radius: 7px; padding: 7px 11px; }
        QToolBar QToolButton:hover { background: #22343d; border-color: #4f707e; }
        #toolbarHint { color: #91a4ae; padding: 0 8px; }
        #panelTitle { font-size: 15px; font-weight: 700; color: #f5fbfc; padding: 4px 2px 8px 2px; }
        #mutedText { color: #8ca0aa; font-size: 9pt; }
        #primaryButton { background: #176a68; border-color: #2db7ad; color: white; font-weight: 600; padding: 9px 16px; }
        #primaryButton:hover { background: #1d7b78; }
        #projectStatus { color: #5eead4; font-weight: 600; padding-left: 8px; }
        #selectionStatus { color: #f4f7f8; font-weight: 700; min-width: 92px; padding: 0 8px; }
        QListWidget, QTreeWidget, QTableWidget, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox, QTabWidget::pane {
            background: #0d1417; color: #e8eef1; border: 1px solid #26363e; border-radius: 7px;
        }
        #chapterList { border-radius: 0; border-left: 0; border-top: 0; border-bottom: 0; }
        QTreeWidget { background: #0d1417; color: #e8eef1; border: 0; }
        QTreeWidget::item { color: #e8eef1; padding: 5px; }
        QTreeWidget::item:selected { background: #1d3a3e; color: #ffffff; }
        QListWidget::item { padding: 9px; margin: 2px 4px; border-radius: 6px; }
        QListWidget::item:selected { background: #1d3a3e; color: #f7ffff; }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox { padding: 6px; selection-background-color: #285d61; selection-color: #ffffff; background: #0d1417; color: #e8eef1; border: 1px solid #26363e; border-radius: 6px; }
        QLineEdit:read-only { color: #bfd0d7; background: #111b20; }
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled { color: #91a4ae; background: #11191d; }
        QComboBox QAbstractItemView { background: #0d1417; color: #e8eef1; selection-background-color: #285d61; selection-color: #ffffff; border: 1px solid #36505c; }
        QComboBox::drop-down { border: 0; width: 24px; }
        QSpinBox, QDoubleSpinBox { color: #e8eef1; }
        QCheckBox { spacing: 7px; }
        QPushButton { background: #1c2a31; border: 1px solid #36505c; padding: 8px 13px; border-radius: 7px; }
        QPushButton:hover { background: #263941; border-color: #52727f; }
        QPushButton:pressed { background: #152127; }
        #collapseButton { padding: 3px 6px; min-height: 24px; max-height: 26px; font-weight: 700; }
        #viewButton { background: #183238; color: #dffefa; border: 1px solid #3b6b70; border-radius: 7px; padding: 7px 11px; font-weight: 600; }
        #viewButton:hover { background: #21444b; }
        QGroupBox { border: 1px solid #273a42; border-radius: 8px; margin-top: 9px; padding-top: 7px; font-weight: 600; color: #dfe9ed; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #84eee0; }
        #liveStatus { background: #0d171a; border: 1px solid #263a40; border-radius: 7px; padding: 8px; }
        QTabBar::tab { background: #10181c; border: 1px solid #24343b; padding: 9px 16px; margin-right: 2px; }
        QTabBar::tab:selected { background: #193237; color: #73f1df; border-bottom-color: #5eead4; }
        QHeaderView::section { background: #172229; color: #cbd8dd; border: 0; border-bottom: 1px solid #31444c; padding: 8px; }
        QTableWidget { gridline-color: #213139; alternate-background-color: #101a1e; }
        QStatusBar { background: #0b1114; border-top: 1px solid #25343c; color: #aebdc3; }
        QSplitter::handle { background: #1d2a30; }
        QScrollBar:vertical { background: #0d1417; width: 12px; }
        QScrollBar::handle:vertical { background: #354a54; min-height: 24px; border-radius: 5px; }
        QScrollBar:horizontal { background: #0d1417; height: 12px; }
        QScrollBar::handle:horizontal { background: #354a54; min-width: 24px; border-radius: 5px; }
    ''')
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
