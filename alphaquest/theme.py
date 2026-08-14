from __future__ import annotations

from copy import deepcopy
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

THEME_KEYS = ("background", "panel", "input", "accent", "accent_hover", "text", "muted", "border", "selection")

PRESETS: dict[str, dict[str, str]] = {
    "Noite Teal": {
        "background": "#11181c", "panel": "#0b1114", "input": "#0d1417",
        "accent": "#176a68", "accent_hover": "#1d7b78", "text": "#e8eef1",
        "muted": "#91a4ae", "border": "#30434c", "selection": "#285d61",
    },
    "FTB Dark": {
        "background": "#171717", "panel": "#101010", "input": "#202020",
        "accent": "#7c4cc7", "accent_hover": "#9565dc", "text": "#f1eef7",
        "muted": "#aaa3b5", "border": "#47404f", "selection": "#5e3d88",
    },
    "Grafite Azul": {
        "background": "#12161d", "panel": "#0c1016", "input": "#151c26",
        "accent": "#2469a8", "accent_hover": "#317fc4", "text": "#edf4fb",
        "muted": "#95a7b8", "border": "#334657", "selection": "#27567d",
    },
    "Claro": {
        "background": "#eef2f5", "panel": "#e2e8ed", "input": "#ffffff",
        "accent": "#087f78", "accent_hover": "#0a978e", "text": "#172027",
        "muted": "#60717d", "border": "#bac8d1", "selection": "#9bd9d5",
    },
}

DEFAULT_PRESET = "Noite Teal"


def _mix_hex(color: str, factor: float) -> str:
    color = color.lstrip("#")
    if len(color) != 6:
        return "#263941"
    rgb = [int(color[i:i+2], 16) for i in (0, 2, 4)]
    if factor >= 0:
        rgb = [round(v + (255-v)*factor) for v in rgb]
    else:
        rgb = [round(v*(1+factor)) for v in rgb]
    return "#" + "".join(f"{max(0,min(255,v)):02x}" for v in rgb)


def normalize_theme(theme: dict[str, str] | None) -> dict[str, str]:
    out = deepcopy(PRESETS[DEFAULT_PRESET])
    if theme:
        for key in THEME_KEYS:
            value = str(theme.get(key, "")).strip()
            if value.startswith("#") and len(value) in (4, 7, 9):
                out[key] = value
    return out


def load_theme(settings: QSettings | None = None) -> tuple[str, dict[str, str]]:
    settings = settings or QSettings("Alpha Devs", "Alpha Quest Editor")
    preset = str(settings.value("theme/preset", DEFAULT_PRESET))
    if preset != "Personalizado" and preset in PRESETS:
        base = deepcopy(PRESETS[preset])
    else:
        base = deepcopy(PRESETS[DEFAULT_PRESET])
    custom = {}
    for key in THEME_KEYS:
        value = settings.value(f"theme/{key}")
        if value:
            custom[key] = str(value)
    if preset == "Personalizado":
        base.update(custom)
    return preset if preset in PRESETS or preset == "Personalizado" else DEFAULT_PRESET, normalize_theme(base)


def save_theme(preset: str, theme: dict[str, str], settings: QSettings | None = None) -> None:
    settings = settings or QSettings("Alpha Devs", "Alpha Quest Editor")
    settings.setValue("theme/preset", preset)
    for key, value in normalize_theme(theme).items():
        settings.setValue(f"theme/{key}", value)
    settings.sync()


def build_stylesheet(theme: dict[str, str]) -> str:
    t = normalize_theme(theme)
    bg, panel, inp = t["background"], t["panel"], t["input"]
    accent, accent_hover, text = t["accent"], t["accent_hover"], t["text"]
    muted, border, selection = t["muted"], t["border"], t["selection"]
    raised = _mix_hex(inp, .08)
    raised2 = _mix_hex(inp, .16)
    dim = _mix_hex(text, -.28)
    accent_soft = _mix_hex(accent, -.20)
    return f'''
        * {{ font-family: "Segoe UI"; font-size: 10pt; }}
        QMainWindow, QWidget {{ background: {bg}; color: {text}; }}
        QMenu {{ background: {panel}; color: {text}; border: 1px solid {border}; padding: 5px; }}
        QMenu::item {{ padding: 7px 24px 7px 10px; border-radius: 5px; }}
        QMenu::item:selected {{ background: {selection}; }}
        QToolBar {{ background: {panel}; border: 0; border-bottom: 1px solid {border}; spacing: 5px; padding: 5px; }}
        QToolBar QToolButton {{ background: {raised}; border: 1px solid {border}; border-radius: 7px; padding: 6px 8px; }}
        QToolBar QToolButton:hover {{ background: {raised2}; border-color: {accent}; }}
        #toolbarHint {{ color: {muted}; padding: 0 8px; }}
        #panelTitle {{ font-size: 15px; font-weight: 700; color: {text}; padding: 4px 2px 8px 2px; }}
        #mutedText {{ color: {muted}; font-size: 9pt; }}
        #primaryButton {{ background: {accent}; border-color: {accent_hover}; color: white; font-weight: 600; padding: 9px 16px; }}
        #primaryButton:hover {{ background: {accent_hover}; }}
        #projectStatus {{ color: {accent_hover}; font-weight: 600; padding-left: 8px; }}
        #selectionStatus {{ color: {text}; font-weight: 700; min-width: 92px; padding: 0 8px; }}
        QListWidget, QTreeWidget, QTableWidget, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox, QTabWidget::pane {{
            background: {inp}; color: {text}; border: 1px solid {border}; border-radius: 7px;
        }}
        #chapterList {{ border-radius: 0; border-left: 0; border-top: 0; border-bottom: 0; }}
        QTreeWidget {{ background: {inp}; color: {text}; border: 0; }}
        QTreeWidget::item {{ color: {text}; padding: 5px; }}
        QTreeWidget::item:selected {{ background: {selection}; color: {text}; }}
        QListWidget::item {{ padding: 9px; margin: 2px 4px; border-radius: 6px; }}
        QListWidget::item:selected {{ background: {selection}; color: {text}; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox {{ padding: 6px; selection-background-color: {selection}; selection-color: {text}; background: {inp}; color: {text}; border: 1px solid {border}; border-radius: 6px; }}
        QLineEdit:read-only {{ color: {dim}; background: {raised}; }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {{ color: {muted}; background: {raised}; }}
        QComboBox QAbstractItemView {{ background: {inp}; color: {text}; selection-background-color: {selection}; selection-color: {text}; border: 1px solid {border}; }}
        QComboBox::drop-down {{ border: 0; width: 24px; }}
        QSpinBox, QDoubleSpinBox {{ color: {text}; }}
        QCheckBox {{ spacing: 7px; }}
        QPushButton {{ background: {raised}; color: {text}; border: 1px solid {border}; padding: 8px 13px; border-radius: 7px; }}
        QPushButton:hover {{ background: {raised2}; border-color: {accent}; }}
        QPushButton:pressed {{ background: {panel}; }}
        #collapseButton {{ padding: 3px 6px; min-height: 24px; max-height: 26px; font-weight: 700; }}
        #viewButton {{ background: {accent_soft}; color: {text}; border: 1px solid {accent}; border-radius: 7px; padding: 6px 8px; font-weight: 600; }}
        #viewButton:hover {{ background: {accent}; }}
        #toolbarCompactButton, #toolbarToggleButton, #toolbarActionButton {{ min-height: 27px; max-height: 31px; padding: 4px 8px; border-radius: 6px; }}
        #toolbarToggleButton:checked {{ background: {accent_soft}; border-color: {accent_hover}; }}
        #toolbarActionButton {{ background: {raised}; }}
        #toolbarActionButton:hover, #toolbarCompactButton:hover, #toolbarToggleButton:hover {{ background: {raised2}; border-color: {accent}; }}
        QGroupBox {{ border: 1px solid {border}; border-radius: 8px; margin-top: 9px; padding-top: 7px; font-weight: 600; color: {text}; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; color: {accent_hover}; }}
        #liveStatus {{ background: {inp}; border: 1px solid {border}; border-radius: 7px; padding: 8px; }}
        QTabBar::tab {{ background: {panel}; color: {text}; border: 1px solid {border}; padding: 9px 16px; margin-right: 2px; }}
        QTabBar::tab:selected {{ background: {accent_soft}; color: {text}; border-bottom-color: {accent_hover}; }}
        QHeaderView::section {{ background: {raised}; color: {text}; border: 0; border-bottom: 1px solid {border}; padding: 8px; }}
        QTableWidget {{ gridline-color: {border}; alternate-background-color: {raised}; }}
        QStatusBar {{ background: {panel}; border-top: 1px solid {border}; color: {muted}; }}
        QSplitter::handle {{ background: {border}; }}
        QScrollBar:vertical {{ background: {inp}; width: 12px; }}
        QScrollBar::handle:vertical {{ background: {border}; min-height: 24px; border-radius: 5px; }}
        QScrollBar:horizontal {{ background: {inp}; height: 12px; }}
        QScrollBar::handle:horizontal {{ background: {border}; min-width: 24px; border-radius: 5px; }}
    '''


def apply_theme(theme: dict[str, str]) -> None:
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(build_stylesheet(theme))
