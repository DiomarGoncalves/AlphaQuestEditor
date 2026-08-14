from __future__ import annotations

import sys
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from .theme import apply_theme, load_theme
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Alpha Quest Editor")
    app.setOrganizationName("Alpha Devs")
    _, theme = load_theme(QSettings("Alpha Devs", "Alpha Quest Editor"))
    apply_theme(theme)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
