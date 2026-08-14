from __future__ import annotations

import logging
import sys
import threading
import traceback

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from .core.diagnostics import configure_logging, logs_dir
from .theme import apply_theme, load_theme
from .ui.main_window import MainWindow
from .version import APP_NAME, APP_VERSION


def _install_exception_hooks(app: QApplication) -> None:
    logger = logging.getLogger("alphaquest.crash")

    def handle(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("Unhandled exception\n%s", details)
        try:
            QMessageBox.critical(
                None,
                "Alpha Quest Editor encontrou um erro",
                f"O erro foi registrado e o programa tentará continuar.\n\n{exc_value}\n\n"
                f"Logs: {logs_dir()}\n\nUse Ajuda → Copiar diagnóstico ao reportar o problema.",
            )
        except Exception:
            pass

    sys.excepthook = handle

    def thread_handle(args):
        details = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        logger.critical("Unhandled thread exception (%s)\n%s", args.thread.name if args.thread else "?", details)

    if hasattr(threading, "excepthook"):
        threading.excepthook = thread_handle


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Alpha Devs")
    _install_exception_hooks(app)
    _, theme = load_theme(QSettings("Alpha Devs", APP_NAME))
    apply_theme(theme)
    win = MainWindow()
    win.show()
    logging.getLogger(__name__).info("Main window ready")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
