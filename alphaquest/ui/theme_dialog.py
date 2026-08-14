from __future__ import annotations

from copy import deepcopy
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QColorDialog, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ..theme import PRESETS, DEFAULT_PRESET, THEME_KEYS, normalize_theme

LABELS = {
    "background": "Fundo geral",
    "panel": "Barras / painéis",
    "input": "Campos / listas",
    "accent": "Cor de destaque",
    "accent_hover": "Destaque ativo",
    "text": "Texto principal",
    "muted": "Texto secundário",
    "border": "Bordas",
    "selection": "Seleção",
}


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self.clicked.connect(self._pick)
        self.setMinimumWidth(150)
        self.set_color(color)

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = QColor(color).name()
        self.setText(self._color.upper())
        fg = "#111111" if QColor(self._color).lightness() > 150 else "#ffffff"
        self.setStyleSheet(f"QPushButton {{ background:{self._color}; color:{fg}; font-weight:700; }}")

    def _pick(self):
        color = QColorDialog.getColor(QColor(self._color), self, "Escolher cor")
        if color.isValid():
            self.set_color(color.name())
            self.colorChanged.emit(self._color)


class ThemeDialog(QDialog):
    previewRequested = Signal(dict)

    def __init__(self, preset: str, theme: dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tema e cores — Alpha Quest Editor")
        self.resize(520, 600)
        self._initial = normalize_theme(theme)
        self._theme = normalize_theme(theme)

        root = QVBoxLayout(self)
        info = QLabel("Escolha um tema pronto ou personalize as cores. A prévia é aplicada imediatamente; Cancelar restaura o tema anterior.")
        info.setWordWrap(True); info.setObjectName("mutedText"); root.addWidget(info)

        row = QHBoxLayout(); row.addWidget(QLabel("Preset"))
        self.preset = QComboBox(); self.preset.addItems(list(PRESETS) + ["Personalizado"])
        self.preset.setCurrentText(preset if preset in PRESETS or preset == "Personalizado" else DEFAULT_PRESET)
        row.addWidget(self.preset, 1); root.addLayout(row)

        form = QFormLayout(); form.setSpacing(10)
        self.buttons: dict[str, ColorButton] = {}
        for key in THEME_KEYS:
            btn = ColorButton(self._theme[key]); btn.colorChanged.connect(lambda value, k=key: self._color_changed(k, value))
            self.buttons[key] = btn; form.addRow(LABELS[key], btn)
        wrap = QWidget(); wrap.setLayout(form); root.addWidget(wrap, 1)

        actions = QHBoxLayout()
        reset = QPushButton("Restaurar Noite Teal"); reset.clicked.connect(lambda:self._apply_preset(DEFAULT_PRESET))
        actions.addWidget(reset); actions.addStretch(1); root.addLayout(actions)

        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Save).setText("Salvar tema")
        box.accepted.connect(self.accept); box.rejected.connect(self.reject); root.addWidget(box)
        self.preset.currentTextChanged.connect(self._preset_changed)

    def _preset_changed(self, name: str):
        if name in PRESETS:
            self._apply_preset(name, update_combo=False)

    def _apply_preset(self, name: str, update_combo: bool = True):
        self._theme = deepcopy(PRESETS[name])
        for key, btn in self.buttons.items(): btn.set_color(self._theme[key])
        if update_combo:
            self.preset.blockSignals(True); self.preset.setCurrentText(name); self.preset.blockSignals(False)
        self.previewRequested.emit(dict(self._theme))

    def _color_changed(self, key: str, value: str):
        self._theme[key] = value
        if self.preset.currentText() != "Personalizado":
            self.preset.blockSignals(True); self.preset.setCurrentText("Personalizado"); self.preset.blockSignals(False)
        self.previewRequested.emit(dict(self._theme))

    def result_theme(self) -> tuple[str, dict[str, str]]:
        return self.preset.currentText(), normalize_theme(self._theme)

    def initial_theme(self) -> dict[str, str]:
        return dict(self._initial)
