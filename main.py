"""PDFim — Profesyonel PDF Editörü  |  PyQt6 + PyMuPDF"""

import sys
import os
import json
import datetime
import traceback

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QFileDialog, QStatusBar,
    QLabel, QWidget, QHBoxLayout, QMessageBox, QSizePolicy,
    QDockWidget, QSpinBox, QMenu, QMenuBar, QInputDialog, QLineEdit,
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QFont, QIcon, QPixmap, QImageReader

from editor import PDFEditor
from viewer import PDFViewerWidget, ThumbnailWidget, EditOverlay
from format_bar import FormatBar


# ── Sabitler ─────────────────────────────────────────────────────────────────

ZOOM_LEVELS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]
DEFAULT_ZOOM = 1.5
MAX_RECENT   = 10
_APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PDFim")
_RECENT_PATH = os.path.join(_APPDATA_DIR, "recent.json")

APP_STYLE = """
* { font-family: "Segoe UI", Arial, sans-serif; }

QMainWindow { background: #1e1e2e; }

QMenuBar {
    background: #13131f;
    color: #cdd6f4;
    border-bottom: 1px solid #2a2a3e;
    font-size: 13px;
    padding: 2px 4px;
}
QMenuBar::item { padding: 4px 10px; border-radius: 4px; }
QMenuBar::item:selected { background: #313244; }
QMenuBar::item:pressed  { background: #45475a; }

QMenu {
    background: #1e1e2e;
    border: 1px solid #313244;
    color: #cdd6f4;
    font-size: 13px;
    padding: 4px 0;
}
QMenu::item { padding: 6px 28px 6px 16px; border-radius: 4px; margin: 1px 4px; }
QMenu::item:selected { background: #313244; }
QMenu::item:disabled  { color: #45475a; }
QMenu::separator { height: 1px; background: #313244; margin: 4px 10px; }
QMenu::icon { margin-left: 8px; }

QToolBar {
    background: #181825;
    border-bottom: 1px solid #2a2a3e;
    spacing: 1px;
    padding: 3px 8px;
}
QToolBar::separator {
    background: #313244;
    width: 1px;
    margin: 4px 4px;
}
QToolButton {
    color: #cdd6f4;
    background: transparent;
    border: none;
    border-radius: 5px;
    padding: 5px 10px;
    font-size: 12px;
    min-width: 28px;
}
QToolButton:hover   { background: #313244; }
QToolButton:pressed { background: #45475a; }
QToolButton:checked { background: #2a2a4a; border: 1px solid #6366f1; color: #89b4fa; }
QToolButton:disabled { color: #45475a; }
QToolBar[compact="true"] QToolButton { padding: 5px 6px; min-width: 20px; }

QStatusBar {
    background: #13131f;
    color: #6c7086;
    border-top: 1px solid #2a2a3e;
    font-size: 11px;
    padding: 0 8px;
}
QStatusBar QLabel { padding: 2px 0; }

QDockWidget {
    color: #cdd6f4;
    font-size: 12px;
    titlebar-close-icon: url(none);
}
QDockWidget::title {
    background: #13131f;
    border-bottom: 1px solid #2a2a3e;
    padding: 5px 8px;
    text-align: left;
    font-size: 11px;
    color: #6c7086;
    letter-spacing: 1px;
    text-transform: uppercase;
}
QDockWidget::close-button, QDockWidget::float-button {
    background: transparent;
    border: none;
    padding: 2px;
    border-radius: 3px;
}
QDockWidget::close-button:hover, QDockWidget::float-button:hover { background: #313244; }

QScrollBar:vertical {
    background: #13131f; width: 8px; border: none;
}
QScrollBar::handle:vertical {
    background: #313244; min-height: 24px; border-radius: 4px; margin: 2px;
}
QScrollBar::handle:vertical:hover { background: #45475a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #13131f; height: 8px; border: none;
}
QScrollBar::handle:horizontal {
    background: #313244; min-width: 24px; border-radius: 4px; margin: 2px;
}
QScrollBar::handle:horizontal:hover { background: #45475a; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QPushButton {
    background: #313244; color: #cdd6f4; border: none;
    border-radius: 6px; padding: 6px 18px; font-size: 13px;
}
QPushButton:hover   { background: #45475a; }
QPushButton:pressed { background: #585b70; }
QPushButton:default { border: 1px solid #6366f1; }

QSpinBox {
    background: #1e1e2e; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 4px;
    padding: 3px 6px; font-size: 12px;
    selection-background-color: #6366f1;
}
QSpinBox:focus { border-color: #6366f1; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; }

QComboBox {
    background: #1e1e2e; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 4px;
    padding: 2px 6px; font-size: 12px; min-height: 20px;
    selection-background-color: #6366f1;
}
QComboBox:focus { border-color: #6366f1; }
QComboBox:disabled { color: #45475a; border-color: #232334; }
QComboBox::drop-down { border: none; width: 16px; }
QComboBox QAbstractItemView {
    background: #1e1e2e; color: #cdd6f4; border: 1px solid #313244;
    selection-background-color: #313244;
}
QToolBar#FormatBar { border-bottom: 1px solid #2a2a3e; background: #1b1b2a; }

QMessageBox { background: #1e1e2e; color: #cdd6f4; }
QMessageBox QLabel { color: #cdd6f4; font-size: 13px; }
"""


# ── Ana Pencere ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDFim")
        self.resize(1280, 860)
        self.setMinimumSize(800, 600)

        self._zoom = DEFAULT_ZOOM
        self._current_mode = "text"
        self._last_copied = ""
        self._last_dir = ""
        self._last_page = 0          # resim eklerken hangi sayfa

        # Undo/redo stacks (PDF bytes snapshots)
        self._undo_stack: list[bytes] = []
        self._redo_stack: list[bytes] = []

        # Çekirdek bileşenler
        self.editor = PDFEditor()
        self.viewer = PDFViewerWidget()
        self._thumbnails = ThumbnailWidget()
        self._fmt = FormatBar(self)
        self._overlay = None             # açık metin düzenleme kutusu (EditOverlay)
        EditOverlay.keep_alive = self._fmt

        # Recent files
        self._recent: list[str] = self._load_recent()

        # UI kurulumu
        self._build_dock()
        self._build_menu_bar()
        self._build_toolbar()
        self._build_status_bar()
        self.setCentralWidget(self.viewer)

        # Sinyaller
        self.viewer.edit_requested.connect(self._on_edit_requested)
        self.viewer.text_drag_done.connect(self._on_text_moved)
        self.viewer.image_drag_done.connect(self._on_image_moved)
        self.viewer.image_delete_req.connect(self._on_image_delete)
        self.viewer.text_select_done.connect(self._on_text_selected)
        self.viewer.area_erase_done.connect(self._on_erase_area)
        self.viewer.image_align_req.connect(self._on_image_align)
        self.viewer.copy_requested.connect(self._on_copy_requested)
        self.viewer.ctrl_scroll.connect(lambda d: self._zoom_in() if d > 0 else self._zoom_out())
        self.viewer._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self._thumbnails.page_selected.connect(self._go_to_page)
        self._fmt.changed.connect(self._preview_format)
        self._fmt.symbol_requested.connect(self._insert_symbol)

    # ── Dock (thumbnail panel) ────────────────────────────────────────────────

    def _build_dock(self):
        dock = QDockWidget("SAYFALAR", self)
        dock.setObjectName("ThumbDock")
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable,
        )
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea,
        )
        dock.setWidget(self._thumbnails)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._thumb_dock = dock

    # ── Menü çubuğu ───────────────────────────────────────────────────────────

    def _build_menu_bar(self):
        mb = self.menuBar()

        # ── Dosya ──
        m_file = mb.addMenu("Dosya")

        act = QAction("Aç…", self)
        act.setShortcut(QKeySequence.StandardKey.Open)
        act.triggered.connect(self._open_file)
        m_file.addAction(act)

        self.act_save = QAction("Kaydet", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.setEnabled(False)
        self.act_save.triggered.connect(self._save_file)
        m_file.addAction(self.act_save)

        self.act_saveas = QAction("Farklı Kaydet…", self)
        self.act_saveas.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_saveas.setEnabled(False)
        self.act_saveas.triggered.connect(self._save_file_as)
        m_file.addAction(self.act_saveas)

        m_file.addSeparator()

        self._recent_menu = QMenu("Son Açılan Dosyalar", self)
        m_file.addMenu(self._recent_menu)
        self._rebuild_recent_menu()

        m_file.addSeparator()
        act_exit = QAction("Çıkış", self)
        act_exit.setShortcut(QKeySequence("Alt+F4"))
        act_exit.triggered.connect(self.close)
        m_file.addAction(act_exit)

        # ── Düzen ──
        m_edit = mb.addMenu("Düzen")

        self.act_undo = QAction("Geri Al", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.setEnabled(False)
        self.act_undo.triggered.connect(self._undo)
        m_edit.addAction(self.act_undo)

        self.act_redo = QAction("Yenile", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.setEnabled(False)
        self.act_redo.triggered.connect(self._redo)
        m_edit.addAction(self.act_redo)

        m_edit.addSeparator()

        self.act_copy = QAction("Kopyala", self)
        self.act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self.act_copy.setEnabled(False)
        self.act_copy.triggered.connect(self._copy_current)
        m_edit.addAction(self.act_copy)

        self.act_select_all = QAction("Sayfadaki Tüm Metni Seç", self)
        self.act_select_all.setShortcut(QKeySequence.StandardKey.SelectAll)
        self.act_select_all.setEnabled(False)
        self.act_select_all.triggered.connect(self._select_page_text)
        m_edit.addAction(self.act_select_all)

        # ── Görünüm ──
        m_view = mb.addMenu("Görünüm")

        act_zi = QAction("Yakınlaş", self)
        act_zi.setShortcut(QKeySequence("Ctrl+="))
        act_zi.triggered.connect(self._zoom_in)
        m_view.addAction(act_zi)

        act_zo = QAction("Uzaklaş", self)
        act_zo.setShortcut(QKeySequence("Ctrl+-"))
        act_zo.triggered.connect(self._zoom_out)
        m_view.addAction(act_zo)

        m_view.addSeparator()

        act_fw = QAction("Genişliğe Sığdır", self)
        act_fw.setShortcut(QKeySequence("Ctrl+W"))
        act_fw.triggered.connect(self._fit_width)
        m_view.addAction(act_fw)

        act_fp = QAction("Sayfaya Sığdır", self)
        act_fp.setShortcut(QKeySequence("Ctrl+Shift+W"))
        act_fp.triggered.connect(self._fit_page)
        m_view.addAction(act_fp)

        m_view.addSeparator()
        m_view.addAction(self._thumb_dock.toggleViewAction())
        self._fmt.toggleViewAction().setText("Biçim Çubuğu")
        m_view.addAction(self._fmt.toggleViewAction())

        # ── Araçlar ──
        m_tools = mb.addMenu("Araçlar")

        act_text = QAction("Metin Modu", self)
        act_text.setShortcut(QKeySequence("Ctrl+1"))
        act_text.triggered.connect(lambda: self._set_mode("text"))
        m_tools.addAction(act_text)

        act_img = QAction("Resim Modu", self)
        act_img.setShortcut(QKeySequence("Ctrl+2"))
        act_img.triggered.connect(lambda: self._set_mode("image"))
        m_tools.addAction(act_img)

        act_sel = QAction("Metin Seç Modu", self)
        act_sel.setShortcut(QKeySequence("Ctrl+3"))
        act_sel.triggered.connect(lambda: self._set_mode("select"))
        m_tools.addAction(act_sel)

        act_erase = QAction("Alan Sil Modu", self)
        act_erase.setShortcut(QKeySequence("Ctrl+4"))
        act_erase.triggered.connect(lambda: self._set_mode("erase"))
        m_tools.addAction(act_erase)

        m_tools.addSeparator()

        self.act_add_img_menu = QAction("Resim Ekle…", self)
        self.act_add_img_menu.setShortcut(QKeySequence("Ctrl+I"))
        self.act_add_img_menu.setEnabled(False)
        self.act_add_img_menu.triggered.connect(self._add_image)
        m_tools.addAction(self.act_add_img_menu)

        # ── Yardım ──
        m_help = mb.addMenu("Yardım")
        act_about = QAction("PDFim Hakkında", self)
        act_about.triggered.connect(self._show_about)
        m_help.addAction(act_about)

    # ── Araç çubuğu ───────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = QToolBar("Ana Araçlar")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        self._tb = tb
        self._tb_labels: list[tuple] = []      # (action, tam etiket, kademe) — dar pencerede kısaltmak için
        self._tb_widths: dict[int, int] = {}   # sıkıştırma kademesi → araç çubuğu genişliği
        self._tb_level = 0

        # Menüde zaten tanımlı kısayollar. Aynı kısayol iki QAction'da olunca Qt onu
        # "belirsiz" sayar ve HİÇBİRİNİ tetiklemez — v1.0'dan beri Ctrl+S, Ctrl+Z,
        # Ctrl+O … bu yüzden çalışmıyordu. Toolbar'da sadece ipucunda gösteriyoruz.
        taken = {a.shortcut().toString() for a in self.findChildren(QAction)
                 if not a.shortcut().isEmpty()}

        # level: pencere daralınca bu düğmenin yazısı hangi kademede gizlenir
        #   1 = ilk (dosya/geri al gibi ikonu tanıdık olanlar), 2 = en son (mod düğmeleri)
        def act(label, shortcut=None, slot=None, checkable=False, enabled=True, tip=None, level=1):
            a = QAction(label, self)
            name = label.split("  ")[-1]
            if shortcut:
                ks = QKeySequence(shortcut)
                if ks.toString() not in taken:
                    a.setShortcut(ks)
                    taken.add(ks.toString())
                a.setToolTip(f"{tip or name}  ({ks.toString(QKeySequence.SequenceFormat.NativeText)})")
            else:
                a.setToolTip(tip or name)
            if "  " in label:
                self._tb_labels.append((a, label, level))
            if slot:
                a.triggered.connect(slot)
            if checkable:
                a.setCheckable(True)
            a.setEnabled(enabled)
            tb.addAction(a)
            return a

        # Dosya
        act("📂  Aç",    "Ctrl+O", self._open_file)
        self.act_save_tb   = act("💾  Kaydet", "Ctrl+S",       self._save_file,   enabled=False)
        self.act_saveas_tb = act("📄  Farklı", "Ctrl+Shift+S", self._save_file_as, enabled=False)

        tb.addSeparator()

        # Undo / Redo
        self.act_undo_tb = act("↩  Geri",  "Ctrl+Z", self._undo,  enabled=False)
        self.act_redo_tb = act("↪  İleri", "Ctrl+Y", self._redo,  enabled=False)
        self.act_copy_tb = act("📋  Kopyala", "Ctrl+C", self._copy_current, enabled=False,
                               tip="Kopyala — tıklanan metni ya da seçili alanı panoya alır")

        tb.addSeparator()

        # Sayfa navigasyonu
        self.act_prev = act("◀", "Ctrl+Left",
                            lambda: self._go_to_page(self.viewer.visible_page() - 1))
        self._page_spin = QSpinBox()
        self._page_spin.setRange(1, 1)
        self._page_spin.setFixedWidth(54)
        self._page_spin.setToolTip("Sayfa numarası")
        self._page_spin.editingFinished.connect(self._on_page_spin)
        tb.addWidget(self._page_spin)

        self._total_lbl = QLabel(" / 1 ")
        self._total_lbl.setStyleSheet("color:#585b70; font-size:12px; padding:0 2px;")
        tb.addWidget(self._total_lbl)

        self.act_next = act("▶", "Ctrl+Right",
                            lambda: self._go_to_page(self.viewer.visible_page() + 1))

        tb.addSeparator()

        # Zoom
        act("−",  "Ctrl+-",         self._zoom_out)
        self._zoom_lbl = QLabel(" 150% ")
        self._zoom_lbl.setStyleSheet(
            "color:#cdd6f4; font-size:12px; min-width:42px; text-align:center; padding:0 2px;")
        tb.addWidget(self._zoom_lbl)
        act("+",  "Ctrl+=",         self._zoom_in)
        act("⇔",  "Ctrl+W",         self._fit_width)
        act("⇕",  "Ctrl+Shift+W",   self._fit_page)

        tb.addSeparator()

        # Mod
        self.act_text_tb = act("✏  Metin",  "Ctrl+1",
                                lambda: self._set_mode("text"), checkable=True, level=2)
        self.act_img_tb  = act("🖼  Resim",  "Ctrl+2",
                                lambda: self._set_mode("image"), checkable=True, level=2)
        self.act_sel_tb  = act("⧉  Metin Seç", "Ctrl+3",
                                lambda: self._set_mode("select"), checkable=True, level=2)
        self.act_erase_tb = act("🩹  Alan Sil", "Ctrl+4",
                                lambda: self._set_mode("erase"), checkable=True, level=2)
        self.act_text_tb.setChecked(True)

        tb.addSeparator()

        self.act_add_img_tb = act("＋  Resim Ekle", "Ctrl+I", self._add_image, enabled=False)

        # İkinci satır: biçim toolbar'ı (metin düzenlenirken etkin)
        self.addToolBarBreak()
        self.addToolBar(self._fmt)

    # ── Durum çubuğu ──────────────────────────────────────────────────────────

    def _build_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_lbl  = QLabel("PDF dosyası açmak için  Ctrl+O")
        self._page_info   = QLabel("")
        self._mode_badge  = QLabel("")
        self._mode_badge.setStyleSheet(
            "color:#a6e3a1; font-size:11px; padding:2px 8px;"
            "background:#1a2a1a; border-radius:8px; margin-right:6px;")
        sb.addWidget(self._status_lbl)
        sb.addPermanentWidget(self._mode_badge)
        sb.addPermanentWidget(self._page_info)

    # ── Mod yönetimi ──────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self._current_mode = mode
        self.viewer.set_mode(mode)
        has_doc = bool(self.editor.doc)
        is_img = mode == "image"

        self.act_add_img_tb.setEnabled(is_img and has_doc)
        self.act_add_img_menu.setEnabled(is_img and has_doc)

        self.act_text_tb.setChecked(mode == "text")
        self.act_img_tb.setChecked(is_img)
        self.act_sel_tb.setChecked(mode == "select")
        self.act_erase_tb.setChecked(mode == "erase")

        if mode == "text":
            self._mode_badge.setText("✏  Metin Modu")
            self._status_lbl.setText(
                "Çift tıkla → düzenle  ·  Sürükle → taşı  ·  Tıkla + Ctrl+C / sağ tık → kopyala")
        elif mode == "select":
            self._mode_badge.setText("⧉  Metin Seç Modu")
            self._status_lbl.setText(
                "Sürükleyerek seç → otomatik kopyalanır  ·  Ctrl+A → tüm sayfa  ·  Sağ tık → menü")
        elif mode == "erase":
            self._mode_badge.setText("🩹  Alan Sil Modu")
            self._status_lbl.setText("Silmek istediğin alanı sürükleyerek seç → üzeri beyazla kapanır")
        else:
            self._mode_badge.setText("🖼  Resim Modu")
            self._status_lbl.setText("Resme tıkla → seç  ·  Sürükle → taşı  ·  Tutamaç → boyutlandır  ·  Del → sil")

    # ── Dosya işlemleri ───────────────────────────────────────────────────────

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "PDF Aç", self._last_dir, "PDF Dosyaları (*.pdf)"
        )
        if path:
            self._last_dir = os.path.dirname(path)
            self._open_file_path(path)

    def _confirm_discard(self) -> bool:
        """Açık belgede kaydedilmemiş değişiklik varsa sor. Devam edilebilirse True."""
        if not (self.editor.doc and self.editor.modified):
            return True
        reply = QMessageBox.question(
            self, "Kaydedilmemiş Değişiklikler",
            f"\"{os.path.basename(self.editor.path)}\" dosyasında kaydedilmemiş değişiklikler var.\n"
            "Kaydetmek ister misiniz?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Save:
            return self._save_file()
        return reply == QMessageBox.StandardButton.Discard

    def _open_file_path(self, path: str):
        if not os.path.exists(path):
            QMessageBox.critical(self, "Hata", f"Dosya bulunamadı:\n{path}")
            return
        if not self._confirm_discard():
            return
        password = None
        while not self.editor.open(path, password):
            if self.editor.needs_password:
                password, ok = QInputDialog.getText(
                    self, "Parola", f"{self.editor.last_error}\n{os.path.basename(path)} için parola:",
                    QLineEdit.EchoMode.Password)
                if ok:
                    continue
                return
            QMessageBox.critical(self, "Hata", f"PDF dosyası açılamadı:\n{path}\n\n{self.editor.last_error}")
            return
        try:
            self._post_open(self.editor.path)
        except Exception as e:
            self._log_exception()
            self.editor.close()
            QMessageBox.critical(self, "Hata", f"PDF görüntülenirken hata oluştu:\n{e}")

    def _post_open(self, path: str):
        name  = os.path.basename(path)
        count = self.editor.page_count()

        self.setWindowTitle(f"PDFim — {name}")
        for a in (self.act_save, self.act_save_tb, self.act_saveas, self.act_saveas_tb,
                  self.act_copy, self.act_select_all, self.act_copy_tb):
            a.setEnabled(True)

        # Undo/redo sıfırla
        self._undo_stack.clear(); self._redo_stack.clear()
        self.act_undo.setEnabled(False); self.act_undo_tb.setEnabled(False)
        self.act_redo.setEnabled(False); self.act_redo_tb.setEnabled(False)

        # Sayfa sayacı
        self._page_spin.setRange(1, count)
        self._total_lbl.setText(f"/ {count} ")
        self._zoom = DEFAULT_ZOOM
        self._zoom_lbl.setText(f" {int(self._zoom*100)}% ")
        self.viewer.zoom = self._zoom

        # Sayfaları yükle
        self.viewer.load_pages(self.editor.render_page, count, images_fn=self.editor.get_images)
        self._set_mode(self._current_mode)
        for i in range(count):
            self._load_text_spans(i)

        # Thumbnails
        self._thumbnails.load(self.editor.render_page, count)

        self._update_page_info(0)
        self._status_lbl.setText(f"Açıldı: {name}  ({count} sayfa)")
        self._save_recent(path)

    def _save_file(self) -> bool:
        if not self.editor.doc:
            return False
        if self.editor.save():
            self.setWindowTitle(self.windowTitle().replace(" *", ""))
            self._status_lbl.setText(f"Kaydedildi: {os.path.basename(self.editor.path)}")
            return True
        box = QMessageBox(QMessageBox.Icon.Critical, "Kayıt Hatası",
                          f"Dosya kaydedilemedi.\n\n{self.editor.last_error}", parent=self)
        btn_as = box.addButton("Farklı Kaydet…", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Vazgeç", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is btn_as:
            return self._save_file_as()
        return False

    def _save_file_as(self) -> bool:
        if not self.editor.doc:
            return False
        start = self.editor.path or self._last_dir
        path, _ = QFileDialog.getSaveFileName(
            self, "Farklı Kaydet", start, "PDF Dosyaları (*.pdf)"
        )
        if not path:
            return False
        self._last_dir = os.path.dirname(path)
        if self.editor.save(path):
            self.setWindowTitle(f"PDFim — {os.path.basename(path)}")
            self._status_lbl.setText(f"Kaydedildi: {os.path.basename(path)}")
            self._save_recent(self.editor.path)
            return True
        QMessageBox.critical(self, "Kayıt Hatası", f"Kaydedilemedi.\n\n{self.editor.last_error}")
        return False

    # ── Son açılan dosyalar ───────────────────────────────────────────────────

    def _load_recent(self) -> list:
        try:
            with open(_RECENT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [p for p in data if os.path.exists(p)][:MAX_RECENT]
        except Exception:
            return []

    def _save_recent(self, path: str):
        self._recent = [path] + [p for p in self._recent if p != path]
        self._recent = self._recent[:MAX_RECENT]
        try:
            os.makedirs(_APPDATA_DIR, exist_ok=True)
            with open(_RECENT_PATH, "w", encoding="utf-8") as f:
                json.dump(self._recent, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        if not self._recent:
            a = QAction("(boş)", self); a.setEnabled(False)
            self._recent_menu.addAction(a)
            return
        for path in self._recent:
            name = os.path.basename(path)
            a = QAction(name, self)
            a.setToolTip(path)
            a.triggered.connect(lambda checked, p=path: self._open_file_path(p))
            self._recent_menu.addAction(a)
        self._recent_menu.addSeparator()
        clr = QAction("Geçmişi Temizle", self)
        clr.triggered.connect(self._clear_recent)
        self._recent_menu.addAction(clr)

    def _clear_recent(self):
        self._recent = []
        try:
            os.remove(_RECENT_PATH)
        except Exception:
            pass
        self._rebuild_recent_menu()

    # ── Zoom ─────────────────────────────────────────────────────────────────

    def _zoom_in(self):
        for z in ZOOM_LEVELS:
            if z > self._zoom + 0.01:
                self._set_zoom_value(z); return

    def _zoom_out(self):
        for z in reversed(ZOOM_LEVELS):
            if z < self._zoom - 0.01:
                self._set_zoom_value(z); return

    def _fit_width(self):
        if not self.editor.doc:
            return
        page   = self.editor.doc[0]
        vp_w   = self.viewer._scroll.viewport().width() - 48
        self._set_zoom_value(vp_w / page.rect.width)

    def _fit_page(self):
        if not self.editor.doc:
            return
        page = self.editor.doc[0]
        vp_w = self.viewer._scroll.viewport().width()  - 48
        vp_h = self.viewer._scroll.viewport().height() - 48
        self._set_zoom_value(min(vp_w / page.rect.width, vp_h / page.rect.height))

    def _set_zoom_value(self, zoom: float):
        self._zoom = max(0.1, min(zoom, 5.0))
        self._zoom_lbl.setText(f" {int(self._zoom*100)}% ")
        if not self.editor.doc:
            return
        cur_page = self.viewer.visible_page()
        self.viewer.set_zoom(
            self._zoom, self.editor.render_page,
            self.editor.page_count(), images_fn=self.editor.get_images,
        )
        for i in range(self.editor.page_count()):
            self._load_text_spans(i)
        QTimer.singleShot(60, lambda: self.viewer.scroll_to_page(cur_page))
        self._update_page_info(cur_page)

    # ── Sayfa navigasyonu ─────────────────────────────────────────────────────

    def _go_to_page(self, page_num: int):
        count = self.editor.page_count() if self.editor.doc else 0
        page_num = max(0, min(page_num, count - 1))
        self.viewer.scroll_to_page(page_num)

    def _on_page_spin(self):
        self._go_to_page(self._page_spin.value() - 1)

    def _on_scroll(self, _):
        if not self.editor.doc:
            return
        page = self.viewer.visible_page()
        self._page_spin.blockSignals(True)
        self._page_spin.setValue(page + 1)
        self._page_spin.blockSignals(False)
        self._thumbnails.set_current(page)
        self._update_page_info(page)

    def _update_page_info(self, page: int):
        count = self.editor.page_count() if self.editor.doc else 0
        self._page_info.setText(
            f"  Sayfa {page+1} / {count}  ·  {int(self._zoom*100)}%  "
        )

    # ── Metin düzenleme ───────────────────────────────────────────────────────

    def _load_text_spans(self, page_num: int):
        lbl = self.viewer.get_page_label(page_num)
        if not lbl or not self.editor.doc:
            return
        zoom = self.viewer.zoom
        page = self.editor.doc[page_num]
        spans = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    x0, y0, x1, y1 = span["bbox"]
                    spans.append({
                        **span,
                        "rect":        span["bbox"],
                        "widget_rect": (x0*zoom, y0*zoom, x1*zoom, y1*zoom),
                    })
        lbl.set_text_spans(spans)

        # Resim hizalama kılavuzları: sayfa kenarları + ortası, metin alanı, metin blokları
        pr = page.rect
        cx0, cy0, cx1, cy1 = self.editor.content_rect(page_num)
        xs = [0, pr.width / 2, pr.width, cx0, cx1]
        ys = [0, pr.height / 2, pr.height, cy0, cy1]
        for bx0, by0, bx1, by1 in self.editor.text_block_rects(page_num):
            xs += [bx0, bx1]; ys += [by0, by1]
        lbl.set_snap_lines([x*zoom for x in xs], [y*zoom for y in ys])

    def _on_edit_requested(self, wx: float, wy: float, page_num: int):
        self._last_page = page_num
        span = self.editor.find_text_at(page_num, wx, wy, self.viewer.zoom)
        if not span:
            return
        lbl = self.viewer.get_page_label(page_num)
        if not lbl:
            return
        x0, y0, x1, y1 = span["rect"]
        zoom = self.viewer.zoom
        # Önce kutu: açık bir önceki düzenleme varsa burada (eski biçimle) kaydedilir
        overlay = lbl.show_edit(
            x0*zoom, y1*zoom, (x1-x0)*zoom, (y1-y0)*zoom,
            span["text"], span["size"],
        )
        self._overlay = overlay
        self._fmt.load(span)
        self._fmt.set_active(True)
        self._preview_format()
        overlay.committed.connect(
            lambda txt, p=page_num, s=span: self._commit_edit(p, s, txt)
        )
        overlay.cancelled.connect(self._end_edit)
        self._status_lbl.setText(
            f"Düzenleniyor: \"{span['text'][:60]}\"  ·  Biçim çubuğundan font/punto/renk  ·  Enter → uygula")

    # ── Biçim toolbar'ı ───────────────────────────────────────────────────────

    def _live_overlay(self):
        """Açık düzenleme kutusu; zoom/geri al sayfaları yeniden kurduysa None"""
        ov = self._overlay
        try:
            if ov is not None and ov.isVisible():
                return ov
        except RuntimeError:             # Qt nesnesi sayfa yenilenince silinmiş
            pass
        self._end_edit()
        return None

    def _preview_format(self):
        ov = self._live_overlay()
        if ov:
            ov.apply_format(self._fmt.format_style(), self._fmt.display_family(), self.viewer.zoom)
            ov.setFocus()

    def _insert_symbol(self, ch: str):
        ov = self._live_overlay()
        if ov:
            ov.insert(ch)
            ov.setFocus()

    def _end_edit(self):
        self._overlay = None
        self._fmt.set_active(False)

    def _commit_edit(self, page_num: int, span: dict, new_text: str):
        style = self._fmt.format_style()
        style_changed = self._fmt.is_modified()
        self._end_edit()
        if new_text == span["text"] and not style_changed:
            return
        if not new_text.strip():
            self._status_lbl.setText("Boş metin uygulanmadı — silmek için 'Alan Sil' modunu kullanın.")
            return
        self._push_snapshot()
        if self.editor.replace_text(page_num, span, new_text, style if style_changed else None):
            self._refresh_page(page_num)
            self._mark_modified()
            self._status_lbl.setText("Metin güncellendi  ·  Ctrl+S ile kaydet")
        else:
            self._undo_stack.pop()
            self._status_lbl.setText("Metin değiştirilemedi.")
            self._sync_undo_redo()

    def _on_text_moved(self, span: dict, wx0: float, wy_base: float, page_num: int):
        zoom = self.viewer.zoom
        self._push_snapshot()
        if self.editor.move_text_span(page_num, span, wx0/zoom, wy_base/zoom):
            self._refresh_page(page_num)
            self._mark_modified()
            self._status_lbl.setText("Metin taşındı  ·  Ctrl+S ile kaydet")
        else:
            self._undo_stack.pop()
            self._status_lbl.setText("Metin taşınamadı.")
            self._sync_undo_redo()

    # ── Metin seçme / kopyalama ───────────────────────────────────────────────

    def _on_text_selected(self, wr: tuple, page_num: int):
        zoom = self.viewer.zoom
        pdf_rect = (wr[0]/zoom, wr[1]/zoom, wr[2]/zoom, wr[3]/zoom)
        txt, rects = self.editor.select_words(page_num, pdf_rect)
        lbl = self.viewer.get_page_label(page_num)
        if lbl:
            lbl.set_selection_highlight([tuple(v*zoom for v in r) for r in rects])
        if not txt:
            self._status_lbl.setText("Seçilen alanda metin yok.")
            return
        self._to_clipboard(txt)

    def _to_clipboard(self, txt: str, what: str = ""):
        if not txt:
            self._status_lbl.setText("Kopyalanacak metin yok.")
            return
        QApplication.clipboard().setText(txt)
        self._last_copied = txt
        preview = txt.replace("\n", " ").replace("\t", " · ")[:50]
        self._status_lbl.setText(f"Kopyalandı{what} ({len(txt)} karakter): \"{preview}\"")

    def _copy_current(self):
        """Ctrl+C: metin modunda tıklanmış metin, yoksa son seçim.
        (Düzenleme kutusu açıkken Ctrl+C'yi kutunun kendisi karşılar.)"""
        if not self.editor.doc:
            return
        if self._current_mode == "text":
            sel = self.viewer.selected_span()
            if sel:
                self._to_clipboard(self.editor.clean_text(sel[1]["text"]).strip())
                return
        if self._last_copied:
            self._to_clipboard(self._last_copied)
        else:
            self._status_lbl.setText(
                "Önce bir metne tıklayın (Metin modu) ya da alan seçin (Metin Seç modu, Ctrl+3).")

    def _select_page_text(self):
        """Ctrl+A: ekrandaki sayfanın tüm metnini seç ve kopyala"""
        if not self.editor.doc:
            return
        page_num = self.viewer.center_page()
        if self._current_mode != "select":
            self._set_mode("select")
        self._on_text_selected(tuple(v * self.viewer.zoom for v in self.editor.doc[page_num].rect),
                               page_num)

    def _on_copy_requested(self, kind: str, span, page_num: int):
        """Sağ tık menüsünden gelen kopyalama istekleri"""
        if kind == "span":
            self._to_clipboard(self.editor.clean_text(span["text"]).strip())
        elif kind == "line":
            self._to_clipboard(self.editor.line_text_at(page_num, span["rect"]), " — satır")
        elif kind == "page":
            if self._current_mode == "select":
                self._select_page_text()
            else:
                self._to_clipboard(self.editor.page_text(page_num), f" — sayfa {page_num + 1}")
        elif kind == "selection":
            self._copy_current()

    def _on_erase_area(self, wr: tuple, page_num: int):
        if not self.editor.doc:
            return
        zoom = self.viewer.zoom
        pdf_rect = (wr[0]/zoom, wr[1]/zoom, wr[2]/zoom, wr[3]/zoom)
        self._push_snapshot()
        if self.editor.erase_area(page_num, pdf_rect):
            self.viewer.refresh_page(page_num, self.editor.render_page,
                                     images=self.editor.get_images(page_num))
            self._load_text_spans(page_num)
            self._thumbnails.refresh_page(page_num, self.editor.render_page)
            self._mark_modified()
            self._status_lbl.setText("Alan silindi  ·  Ctrl+S ile kaydet")
        else:
            self._undo_stack.pop()
            self._status_lbl.setText("Alan silinemedi.")
            self._sync_undo_redo()

    # ── Resim işlemleri ───────────────────────────────────────────────────────

    def _on_image_moved(self, img_info: dict, new_wr: tuple, page_num: int):
        zoom = self.viewer.zoom
        wx0, wy0, wx1, wy1 = new_wr
        self._apply_image_rect(page_num, img_info, (wx0/zoom, wy0/zoom, wx1/zoom, wy1/zoom),
                               "Resim taşındı")

    def _on_image_align(self, img_info: dict, how: str, page_num: int):
        """Sağ tık → Hizala. Yatayda/dikeyde metin alanına (kenar boşluklarına) göre
        kenarlara, sayfanın tam ortasına göre ortalar."""
        x0, y0, x1, y1 = img_info["rect"]
        w, h = x1 - x0, y1 - y0
        cx0, cy0, cx1, cy1 = self.editor.content_rect(page_num)
        pr = self.editor.doc[page_num].rect
        if   how == "left":    x0 = cx0
        elif how == "right":   x0 = cx1 - w
        elif how == "hcenter": x0 = (pr.width - w) / 2
        elif how == "top":     y0 = cy0
        elif how == "bottom":  y0 = cy1 - h
        elif how == "vcenter": y0 = (pr.height - h) / 2
        self._apply_image_rect(page_num, img_info, (x0, y0, x0 + w, y0 + h), "Resim hizalandı")

    def _apply_image_rect(self, page_num: int, img_info: dict, pdf_rect: tuple, msg: str):
        self._last_page = page_num
        self._push_snapshot()
        if self.editor.move_image(page_num, img_info, pdf_rect):
            imgs = self.editor.get_images(page_num)
            self.viewer.refresh_page(page_num, self.editor.render_page, images=imgs)
            self._thumbnails.refresh_page(page_num, self.editor.render_page)
            self._mark_modified()
            self._status_lbl.setText(f"{msg}  ·  Ctrl+S ile kaydet")
        else:
            self._undo_stack.pop()
            self._status_lbl.setText("Resim taşınamadı.")
            self._sync_undo_redo()

    def _on_image_delete(self, img_info: dict, page_num: int):
        reply = QMessageBox.question(
            self, "Resmi Sil",
            "Bu resmi PDF'den kalıcı olarak silmek istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._push_snapshot()
        if self.editor.delete_image(page_num, img_info):
            imgs = self.editor.get_images(page_num)
            self.viewer.refresh_page(page_num, self.editor.render_page, images=imgs)
            self._thumbnails.refresh_page(page_num, self.editor.render_page)
            self._mark_modified()
            self._status_lbl.setText("Resim silindi  ·  Ctrl+S ile kaydet")
        else:
            self._undo_stack.pop()
            self._status_lbl.setText("Resim silinemedi.")
            self._sync_undo_redo()

    def _delete_selected_image(self):
        lbl = self.viewer.get_page_label(self._last_page)
        if lbl:
            sel = lbl.get_selected()
            if sel:
                self._on_image_delete(sel, self._last_page)
                return
        self._status_lbl.setText("Önce resim modunda bir resim seçin.")

    def _add_image(self):
        if not self.editor.doc:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Resim Seç", self._last_dir,
            "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp)"
        )
        if not path:
            return
        # Eskiden en son dokunulan sayfaya (çoğu zaman 1. sayfa) ekliyordu;
        # artık ekranda bakılan sayfaya.
        page_num = self.viewer.center_page()
        page = self.editor.doc[page_num]
        pw, ph = page.rect.width, page.rect.height

        # Kutu resmin kendi en/boy oranında: kare kutuya sığdırınca resim kutunun
        # ortasında kalıyor, seçim çerçevesi resimle örtüşmüyordu.
        size = QImageReader(path).size()
        iw, ih = (size.width(), size.height()) if size.isValid() else (1, 1)
        cx0, _, cx1, _ = self.editor.content_rect(page_num)
        w = min(cx1 - cx0, pw * 0.4)
        h = w * ih / iw
        if h > ph * 0.4:
            h = ph * 0.4; w = h * iw / ih
        x0, y0 = (pw - w) / 2, (ph - h) / 2
        rect = (x0, y0, x0 + w, y0 + h)

        self._push_snapshot()
        if self.editor.insert_image_file(page_num, rect, path):
            imgs = self.editor.get_images(page_num)
            self.viewer.refresh_page(page_num, self.editor.render_page, images=imgs)
            self._thumbnails.refresh_page(page_num, self.editor.render_page)
            self._mark_modified()
            self._last_page = page_num
            z = self.viewer.zoom
            lbl = self.viewer.get_page_label(page_num)
            if lbl:
                lbl.select_image_near(tuple(v * z for v in rect))
            self._status_lbl.setText(
                f"Resim eklendi: {os.path.basename(path)}  ·  Sürükle → kılavuzlara yapışır  ·  "
                "Sağ tık → Hizala  ·  Alt → serbest")
        else:
            self._undo_stack.pop()
            self._sync_undo_redo()
            QMessageBox.critical(self, "Hata", "Resim eklenemedi. Desteklenmeyen format olabilir.")

    # ── Undo / Redo ──────────────────────────────────────────────────────────

    def _push_snapshot(self):
        if not self.editor.doc:
            return
        self._undo_stack.append(self.editor.doc.tobytes())
        if len(self._undo_stack) > 20:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._sync_undo_redo()

    def _undo(self):
        if not self._undo_stack or not self.editor.doc:
            return
        self._redo_stack.append(self.editor.doc.tobytes())
        self.editor.open_from_bytes(self._undo_stack.pop(), self.editor.path)
        self._reload_all_pages()
        self._sync_undo_redo()
        self._status_lbl.setText("Geri alındı.")

    def _redo(self):
        if not self._redo_stack or not self.editor.doc:
            return
        self._undo_stack.append(self.editor.doc.tobytes())
        self.editor.open_from_bytes(self._redo_stack.pop(), self.editor.path)
        self._reload_all_pages()
        self._sync_undo_redo()
        self._status_lbl.setText("Yenilendi.")

    def _reload_all_pages(self):
        count    = self.editor.page_count()
        cur_page = self.viewer.visible_page()
        self.viewer.load_pages(
            self.editor.render_page, count,
            images_fn=self.editor.get_images,
        )
        self._set_mode(self._current_mode)
        for i in range(count):
            self._load_text_spans(i)
        self._thumbnails.load(self.editor.render_page, count)
        QTimer.singleShot(60, lambda: self.viewer.scroll_to_page(cur_page))
        self._update_page_info(cur_page)

    def _sync_undo_redo(self):
        has_undo = bool(self._undo_stack)
        has_redo = bool(self._redo_stack)
        self.act_undo.setEnabled(has_undo)
        self.act_undo_tb.setEnabled(has_undo)
        self.act_redo.setEnabled(has_redo)
        self.act_redo_tb.setEnabled(has_redo)

    # ── Yardımcılar ───────────────────────────────────────────────────────────

    def _refresh_page(self, page_num: int):
        self.viewer.refresh_page(page_num, self.editor.render_page)
        self._load_text_spans(page_num)
        self._thumbnails.refresh_page(page_num, self.editor.render_page)

    def _mark_modified(self):
        if " *" not in self.windowTitle():
            self.setWindowTitle(self.windowTitle() + " *")
        self.editor.modified = True

    def _show_about(self):
        QMessageBox.about(
            self, "PDFim Hakkında",
            "<h2 style='color:#cdd6f4; margin:0'>PDFim</h2>"
            "<p style='color:#a6adc8'>Sürüm 1.4  —  PDF Editörü</p>"
            "<p style='color:#6c7086; font-size:12px'>"
            "PyMuPDF + PyQt6 ile geliştirildi.<br>"
            "Metin düzenleme · Biçim çubuğu · Metin kopyalama · Resim hizalama · Orijinal font desteği"
            "</p>",
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_toolbar_density()

    def _set_toolbar_level(self, level: int):
        """0 = tüm yazılar, 1 = dosya/düzen düğmeleri sadece ikon, 2 = hepsi ikon + dar boşluk"""
        for a, label, lvl in self._tb_labels:
            a.setText(label.split("  ")[0] if level >= lvl else label)
        compact = "true" if level >= 2 else "false"
        if self._tb.property("compact") != compact:
            self._tb.setProperty("compact", compact)
            for w in self._tb.findChildren(QWidget):   # stylesheet'teki [compact] seçicisi yeniden uygulansın
                w.style().unpolish(w); w.style().polish(w)
        self._tb_level = level

    def _apply_toolbar_density(self):
        """Pencere daraldıkça önce ikincil düğmelerin, sonra mod düğmelerinin yazısını gizle.
        Qt aksi hâlde yazıları "…det" gibi kırpıyordu; tam ad ipucunda (tooltip) kalır."""
        if not getattr(self, "_tb_labels", None) or not self.isVisible():
            return
        if not self._tb_widths:                   # her kademenin genişliğini bir kez ölç
            for level in (0, 1, 2):
                self._set_toolbar_level(level)
                self._tb_widths[level] = self._tb.sizeHint().width()
        avail = self.width() - 12
        level = next((lv for lv in (0, 1) if self._tb_widths[lv] <= avail), 2)
        if level != self._tb_level or not self._tb.property("compact"):
            self._set_toolbar_level(level)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_toolbar_density()

    def closeEvent(self, event):
        # Kayıt başarısız olursa pencere açık kalır — eskiden hata mesajından
        # sonra yine kapanıyor ve tüm değişiklikler kayboluyordu.
        if not self._confirm_discard():
            event.ignore(); return
        self.editor.close()
        event.accept()

    def _log_exception(self):
        _write_crash_log(*sys.exc_info())


# ── Uygulama giriş noktası ────────────────────────────────────────────────────

def _write_crash_log(exc_type, exc_value, exc_tb):
    try:
        os.makedirs(_APPDATA_DIR, exist_ok=True)
        with open(os.path.join(_APPDATA_DIR, "crash.log"), "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.datetime.now().isoformat()} ===\n")
            f.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    except Exception:
        pass


def _setup_crash_handler():
    def handler(exc_type, exc_value, exc_tb):
        _write_crash_log(exc_type, exc_value, exc_tb)
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = handler


def main():
    _setup_crash_handler()
    app = QApplication(sys.argv)
    app.setApplicationName("PDFim")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    # Uygulama geneli varsayılan font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    win = MainWindow()
    win.show()

    # Dosya ilişkilendirme: PDFim.exe dosya.pdf
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        win._open_file_path(sys.argv[1])

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
