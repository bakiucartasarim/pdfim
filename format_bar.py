"""Metin biçim toolbar'ı — font, punto, kalın/italik/altı çizili, renk, hizalama, semboller

Sadece bir metin düzenlenirken etkindir; seçilen biçim düzenlenen metnin tamamına
Enter'da uygulanır. PDF'te paragraf yapısı olmadığı için iki yana yaslama, madde
işareti, satır aralığı gibi Word düğmeleri bilerek yok.
"""

from PyQt6.QtWidgets import (
    QToolBar, QComboBox, QToolButton, QMenu, QColorDialog, QCompleter, QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QIcon, QPixmap, QPainter, QKeySequence

import fonts

SIZES = [6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 36, 48, 72]

# Datasheet'lerde sık geçen, klavyede olmayan karakterler
SYMBOLS = [
    ("²", "kare"), ("³", "küp"), ("°", "derece"), ("µ", "mikro"), ("Ω", "ohm"),
    ("±", "artı-eksi"), ("×", "çarpı"), ("÷", "bölü"), ("≤", "küçük eşit"), ("≥", "büyük eşit"),
    ("≈", "yaklaşık"), ("≠", "eşit değil"), ("‰", "binde"), ("½", "yarım"), ("¼", "çeyrek"),
    ("Ø", "çap"), ("•", "madde"), ("→", "ok"), ("™", "ticari marka"), ("®", "tescilli"), ("©", "telif"),
]


def _color_icon(rgb: int) -> QIcon:
    pm = QPixmap(16, 16)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(QColor("#6c7086"))
    p.setBrush(QColor(f"#{rgb:06x}"))
    p.drawRect(1, 1, 13, 13)
    p.end()
    return QIcon(pm)


class FormatBar(QToolBar):
    changed = pyqtSignal()               # biçimde bir değişiklik oldu → önizlemeyi güncelle
    symbol_requested = pyqtSignal(str)   # düzenleme kutusuna karakter ekle

    def __init__(self, parent=None):
        super().__init__("Biçim", parent)
        self.setObjectName("FormatBar")
        self.setMovable(False)
        self._loading = False
        self._initial: dict | None = None
        self._orig_family: str | None = None
        self._color = 0x000000

        self.addWidget(self._caption("Font"))
        self.family_box = QComboBox()
        self.family_box.setEditable(True)
        self.family_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.family_box.setMinimumWidth(200)
        self.family_box.setMaxVisibleItems(20)
        self.family_box.setToolTip("Font ailesi — 'Orijinal' belgedeki fontu korur")
        self.family_box.addItem("Orijinal font", None)
        for fam in sorted(fonts.system_fonts(), key=str.lower):
            self.family_box.addItem(fam, fam)
        comp = self.family_box.completer()
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.family_box.activated.connect(self._emit)
        self.family_box.lineEdit().editingFinished.connect(self._emit)
        self.addWidget(self.family_box)

        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        self.size_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.size_box.setFixedWidth(64)
        self.size_box.setToolTip("Punto")
        for s in SIZES:
            self.size_box.addItem(str(s))
        self.size_box.activated.connect(self._emit)
        self.size_box.lineEdit().editingFinished.connect(self._emit)
        self.addWidget(self.size_box)

        self.addSeparator()
        self.act_bold = self._toggle("B", "Kalın (Ctrl+B)", "Ctrl+B", bold=True)
        self.act_italic = self._toggle("I", "İtalik", None, italic=True)
        self.act_underline = self._toggle("U", "Altı çizili (Ctrl+U)", "Ctrl+U", underline=True)

        self.color_btn = QToolButton()
        self.color_btn.setToolTip("Metin rengi")
        self.color_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.color_btn.clicked.connect(self._pick_color)
        self.addWidget(self.color_btn)

        self.addSeparator()
        grp = QActionGroup(self)
        grp.setExclusive(True)
        self.act_left = self._toggle("⇤", "Sola yasla (orijinal konum)", None, group=grp)
        self.act_center = self._toggle("↔", "Orijinal kutuda ortala", None, group=grp)
        self.act_right = self._toggle("⇥", "Orijinal kutuda sağa yasla — tablo değerleri için", None, group=grp)

        self.addSeparator()
        sym = QToolButton()
        sym.setText("Ω")
        sym.setToolTip("Sembol ekle (², °, µ, ± …)")
        sym.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        sym.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(sym)
        for ch, name in SYMBOLS:
            menu.addAction(f"{ch}    {name}").triggered.connect(
                lambda _=False, c=ch: self.symbol_requested.emit(c))
        sym.setMenu(menu)
        self.addWidget(sym)

        act_reset = QAction("↺", self)
        act_reset.setToolTip("Biçimi orijinaline döndür")
        act_reset.triggered.connect(self._reset)
        self.addAction(act_reset)
        self.widgetForAction(act_reset).setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._set_color(0x000000)
        self.set_active(False)

    # ── Kurulum yardımcıları ──────────────────────────────────────────────────

    def _caption(self, text):
        lbl = QLabel(f" {text} ")
        lbl.setStyleSheet("color:#6c7086; font-size:11px;")
        return lbl

    def _toggle(self, text, tip, shortcut, group=None, bold=False, italic=False, underline=False):
        a = QAction(text, self)
        a.setCheckable(True)
        a.setToolTip(tip)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        f = a.font()
        f.setBold(bold); f.setItalic(italic); f.setUnderline(underline)
        a.setFont(f)
        if group:
            group.addAction(a)
        a.toggled.connect(self._emit)
        self.addAction(a)
        # Toolbar'a tıklamak düzenleme kutusundan odağı çalmasın
        self.widgetForAction(a).setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return a

    # ── Dış API ───────────────────────────────────────────────────────────────

    def set_active(self, on: bool):
        self.setEnabled(on)
        for a in self.actions():         # Ctrl+B / Ctrl+U kısayolları da kapansın
            a.setEnabled(on)

    def load(self, span: dict):
        """Düzenlenecek metnin mevcut biçimini göster"""
        self._loading = True
        flags = span.get("flags", 0)
        self._orig_family = fonts.match_family(span.get("font", ""))
        pdf_name = span.get("font", "").split("+")[-1]
        self.family_box.setItemText(0, f"Orijinal — {self._orig_family or pdf_name or '?'}")
        self.family_box.setCurrentIndex(0)
        self.size_box.setCurrentText(f"{round(span.get('size', 10), 1):g}")
        self.act_bold.setChecked(bool(flags & 16))
        self.act_italic.setChecked(bool(flags & 2))
        self.act_underline.setChecked(False)
        self.act_left.setChecked(True)
        self._set_color(span.get("color", 0))
        self._loading = False
        self._initial = self.format_style()

    def format_style(self) -> dict:
        idx = self.family_box.findText(self.family_box.currentText(), Qt.MatchFlag.MatchFixedString)
        family = self.family_box.itemData(idx) if idx > 0 else None
        try:
            size = float(self.size_box.currentText().replace(",", "."))
            size = min(max(size, 1.0), 400.0)
        except ValueError:
            size = self._initial["size"] if self._initial else 10.0
        align = "center" if self.act_center.isChecked() else "right" if self.act_right.isChecked() else "left"
        return {
            "family": family,
            "size": size,
            "bold": self.act_bold.isChecked(),
            "italic": self.act_italic.isChecked(),
            "underline": self.act_underline.isChecked(),
            "color": self._color,
            "align": align,
        }

    def display_family(self) -> str:
        """Önizlemede kullanılacak Qt font ailesi"""
        return self.format_style()["family"] or self._orig_family or "Arial"

    def is_modified(self) -> bool:
        return self._initial is not None and self.format_style() != self._initial

    # ── İç olaylar ────────────────────────────────────────────────────────────

    def _emit(self, *_):
        if not self._loading:
            self.changed.emit()

    def _set_color(self, rgb: int):
        self._color = rgb & 0xFFFFFF
        self.color_btn.setIcon(_color_icon(self._color))

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(f"#{self._color:06x}"), self, "Metin rengi")
        if c.isValid():
            self._set_color((c.red() << 16) | (c.green() << 8) | c.blue())
        self._emit()                     # iptal edilse de odağı düzenleme kutusuna geri ver

    def _reset(self):
        if not self._initial:
            return
        st = self._initial
        self._loading = True
        self.family_box.setCurrentIndex(0)
        self.size_box.setCurrentText(f"{round(st['size'], 1):g}")
        self.act_bold.setChecked(st["bold"])
        self.act_italic.setChecked(st["italic"])
        self.act_underline.setChecked(st["underline"])
        self.act_left.setChecked(True)
        self._set_color(st["color"])
        self._loading = False
        self._emit()
