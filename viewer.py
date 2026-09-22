"""PDF sayfa görüntüleyici — PageLabel, ThumbnailWidget, PDFViewerWidget"""

def _log(msg): pass

from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QLabel, QVBoxLayout, QLineEdit,
    QSizePolicy, QListWidget, QListWidgetItem, QMenu, QApplication,
)
from PyQt6.QtCore import Qt, QPoint, QRect, QRectF, QSize, pyqtSignal
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QFont, QBrush, QIcon
)


# ── Metin düzenleme overlay ───────────────────────────────────────────────────

class EditOverlay(QLineEdit):
    committed = pyqtSignal(str)
    cancelled = pyqtSignal()

    # Odak bu widget'ın içine geçerse (biçim toolbar'ı) düzenleme kapanmaz
    keep_alive: "QWidget | None" = None

    def __init__(self, parent, text: str, rect: QRect, fontsize: float):
        super().__init__(parent)
        self._done = False
        self.setText(text)
        self.setGeometry(rect)
        self.apply_format({"size": fontsize, "bold": False, "italic": False,
                           "underline": False, "color": 0x111111, "align": "left"},
                          "Segoe UI", 1.0)
        self.textChanged.connect(self._fit_width)
        self.selectAll()
        self.setFocus()
        self.show()

    def apply_format(self, st: dict, family: str, zoom: float):
        """Biçim toolbar'ındaki seçimi canlı önizle.

        Uygulama geneli stylesheet (`* { font-family: ... }`) setFont()'u ezdiği
        için font da stylesheet ile veriliyor.
        """
        px = max(9, round(st["size"] * zoom))
        align = {"center": Qt.AlignmentFlag.AlignHCenter,
                 "right": Qt.AlignmentFlag.AlignRight}.get(st["align"], Qt.AlignmentFlag.AlignLeft)
        self.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(f"""
            QLineEdit {{
                background: #fffde7;
                border: 2px solid #f59e0b;
                border-radius: 2px;
                color: #{st['color']:06x};
                padding: 0 2px;
                font-family: "{family}";
                font-size: {px}px;
                font-weight: {'bold' if st['bold'] else 'normal'};
                font-style: {'italic' if st['italic'] else 'normal'};
                text-decoration: {'underline' if st['underline'] else 'none'};
            }}
        """)
        if self.height() < px + 8:
            self.resize(self.width(), px + 8)
        self._fit_width()

    def _fit_width(self, *_):
        """Kalın/büyük font ya da uzayan metin kutuya sığsın (baş harfler kaymasın)"""
        self.ensurePolished()
        need = self.fontMetrics().horizontalAdvance(self.text() + "  ") + 12
        if need > self.width():
            self.resize(need, self.height())

    def _finish(self, commit: bool):
        if self._done:
            return
        self._done = True           # hide() da focusOut tetikler — ikinci kez işlenmesin
        if commit:
            self.committed.emit(self.text())
        else:
            self.cancelled.emit()
        self.hide()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish(True)
        elif event.key() == Qt.Key.Key_Escape:
            self._finish(False)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # Açılır menü / renk seçici penceresi ya da biçim toolbar'ı → düzenleme sürüyor
        if event.reason() in (Qt.FocusReason.PopupFocusReason,
                              Qt.FocusReason.ActiveWindowFocusReason):
            return
        fw = QApplication.focusWidget()
        if self.keep_alive is not None and fw is not None and \
                (fw is self.keep_alive or self.keep_alive.isAncestorOf(fw)):
            return
        self._finish(True)


# ── Tek sayfa widget'ı ────────────────────────────────────────────────────────

class PageLabel(QLabel):
    """Tek sayfa — metin seç/taşı/düzenle + resim seç/taşı/boyutlandır/sil"""
    text_edit_requested = pyqtSignal(float, float)
    text_drag_done      = pyqtSignal(dict, float, float)
    image_drag_done     = pyqtSignal(dict, tuple)
    image_delete_req    = pyqtSignal(dict)
    text_select_done    = pyqtSignal(tuple)   # (wx0, wy0, wx1, wy1) widget koordinatında
    area_erase_done     = pyqtSignal(tuple)   # aynı — "alan sil" modu
    image_align_req     = pyqtSignal(dict, str)   # (resim, "left"|"hcenter"|"right"|"top"|"vcenter"|"bottom")
    copy_requested      = pyqtSignal(str, object) # ("span"|"line"|"page"|"selection", span | None)

    SNAP_PX = 6   # bu kadar piksel yakına gelince kılavuz çizgiye yapışır

    _HANDLE_CURSORS = {
        "nw": Qt.CursorShape.SizeFDiagCursor, "ne": Qt.CursorShape.SizeBDiagCursor,
        "sw": Qt.CursorShape.SizeBDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
        "n":  Qt.CursorShape.SizeVerCursor,   "s":  Qt.CursorShape.SizeVerCursor,
        "w":  Qt.CursorShape.SizeHorCursor,   "e":  Qt.CursorShape.SizeHorCursor,
    }

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._mode = "text"
        self._overlay: EditOverlay | None = None
        self._text_spans: list = []
        self._text_sel: dict | None = None
        self._text_drag_start: QPoint | None = None
        self._text_drag_orig_wr: tuple | None = None
        self._text_drag_cur_wr: tuple | None = None
        self._images: list[dict] = []
        self._selected: dict | None = None
        self._drag_start: QPoint | None = None
        self._drag_orig: tuple | None = None
        self._drag_cur: tuple | None = None
        self._resize_handle: str | None = None
        # Metin seçme (marquee) modu
        self._sel_start: QPoint | None = None
        self._sel_cur: QPoint | None = None
        # Hizalama: sayfa/metin kılavuzları (widget koordinatı) + o an aktif yapışmalar
        self._snap_xs: list[float] = []
        self._snap_ys: list[float] = []
        self._guides: list[tuple] = []        # ("v", x) / ("h", y)
        # Metin Seç modunda kopyalanan kelimelerin kutuları (widget koordinatı)
        self._sel_highlight: list[tuple] = []

    # ── Mod & veri ───────────────────────────────────────────────────────────

    def set_mode(self, mode: str):
        self._mode = mode
        self._selected = None; self._drag_start = None
        self._drag_cur = None; self._resize_handle = None
        self._text_sel = None; self._text_drag_start = None
        self._text_drag_cur_wr = None
        self._sel_start = None; self._sel_cur = None
        self._sel_highlight = []
        cursor = (Qt.CursorShape.CrossCursor if mode in ("select", "erase")
                  else Qt.CursorShape.ArrowCursor)
        self.setCursor(cursor)
        self.update()

    def set_images(self, images: list, zoom: float):
        self._images = []
        for img in images:
            x0, y0, x1, y1 = img["rect"]
            self._images.append({**img, "widget_rect": (x0*zoom, y0*zoom, x1*zoom, y1*zoom)})
        self._selected = None
        self.update()

    def set_text_spans(self, spans: list):
        self._text_spans = spans

    def set_snap_lines(self, xs: list, ys: list):
        self._snap_xs, self._snap_ys = xs, ys

    def set_selection_highlight(self, rects: list):
        self._sel_highlight = rects
        self.update()

    def has_selection(self) -> bool:
        return bool(self._sel_highlight)

    def get_text_selection(self) -> "dict | None":
        """Metin modunda tek tıkla seçilmiş (kesikli çerçeveli) span"""
        return self._text_sel if self._mode == "text" else None

    def get_selected(self) -> "dict | None":
        return self._selected

    def select_image_near(self, wr: tuple):
        """Verilen dikdörtgene en yakın resmi seç (yeni eklenen resmi seçili getirmek için)"""
        if not self._images:
            return
        cx, cy = (wr[0] + wr[2]) / 2, (wr[1] + wr[3]) / 2
        def dist(img):
            x0, y0, x1, y1 = img["widget_rect"]
            return abs((x0 + x1) / 2 - cx) + abs((y0 + y1) / 2 - cy)
        self._selected = min(self._images, key=dist)
        self.setFocus(); self.update()

    # ── Overlay ──────────────────────────────────────────────────────────────

    def show_edit(self, wx: float, wy_bottom: float, w: float, h: float,
                  text: str, fontsize: float):
        if self._overlay:
            self._overlay.hide()
        rect = QRect(int(wx), int(wy_bottom - h), int(max(w, 80)), int(h + 4))
        self._overlay = EditOverlay(self, text, rect, fontsize)
        return self._overlay

    # ── Mouse ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.pos()
        if self._mode in ("select", "erase"):
            self._sel_start = pos
            self._sel_cur = pos
            self._sel_highlight = []
            self.setFocus(); self.update()
            return
        if self._mode == "image":
            handle = self._handle_at(pos.x(), pos.y()) if self._selected else None
            if handle:
                self._resize_handle = handle
                self._drag_start = pos
                self._drag_orig = self._selected["widget_rect"]
                self._drag_cur = None
            else:
                hit = self._image_at(pos.x(), pos.y())
                if hit:
                    self._selected = hit; self._resize_handle = None
                    self._drag_start = pos; self._drag_orig = hit["widget_rect"]
                    self._drag_cur = None
                else:
                    self._selected = None; self._resize_handle = None
                    self._drag_start = None
            self.setFocus(); self.update()
        else:
            self._text_drag_cur_wr = None
            span = self._span_at(pos.x(), pos.y())
            if span:
                self._text_sel = span; self._text_drag_start = pos
                x0, y0, x1, y1 = span["widget_rect"]
                self._text_drag_orig_wr = (x0, y0, x1, y1)
            else:
                self._text_sel = None; self._text_drag_start = None
            self.setFocus(); self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._mode == "text":
            self._text_drag_start = None; self._text_drag_cur_wr = None
            self.text_edit_requested.emit(float(event.pos().x()), float(event.pos().y()))

    def mouseMoveEvent(self, event):
        if self._mode in ("select", "erase"):
            if event.buttons() & Qt.MouseButton.LeftButton and self._sel_start:
                self._sel_cur = event.pos()
                self.update()
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            if self._mode == "image":
                self._update_cursor(event.pos().x(), event.pos().y())
            elif self._mode == "text":
                hit = self._span_at(event.pos().x(), event.pos().y())
                self.setCursor(Qt.CursorShape.SizeAllCursor if hit else Qt.CursorShape.ArrowCursor)
            return
        if self._mode == "image":
            if not self._selected or not self._drag_start:
                return
            mods = event.modifiers()
            snap = not (mods & Qt.KeyboardModifier.AltModifier)       # Alt → serbest
            if self._resize_handle:
                keep_ratio = not (mods & Qt.KeyboardModifier.ShiftModifier)  # Shift → oransız
                self._drag_cur = self._compute_resize(event.pos(), snap, keep_ratio)
            else:
                d = event.pos() - self._drag_start
                ox0, oy0, ox1, oy1 = self._drag_orig
                w, h = ox1-ox0, oy1-oy0
                self._drag_cur = self._snap_move((ox0+d.x(), oy0+d.y(), ox0+d.x()+w, oy0+d.y()+h), snap)
            self.update()
        elif self._mode == "text":
            if not self._text_sel or not self._text_drag_start:
                return
            delta = event.pos() - self._text_drag_start
            if delta.manhattanLength() < 4:
                return
            ox0, oy0, ox1, oy1 = self._text_drag_orig_wr
            w, h = ox1-ox0, oy1-oy0
            self._text_drag_cur_wr = (ox0+delta.x(), oy0+delta.y(), ox0+delta.x()+w, oy0+delta.y()+h)
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._mode in ("select", "erase"):
            if self._sel_start and self._sel_cur:
                a, b = self._sel_start, self._sel_cur
                wr = (min(a.x(), b.x()), min(a.y(), b.y()),
                      max(a.x(), b.x()), max(a.y(), b.y()))
                mode = self._mode
                self._sel_start = None; self._sel_cur = None
                self.update()
                if wr[2] - wr[0] > 3 and wr[3] - wr[1] > 3:
                    if mode == "select":
                        self.text_select_done.emit(wr)
                    else:
                        self.area_erase_done.emit(wr)
            return
        if self._mode == "image":
            self._guides = []
            if self._selected and self._drag_cur:
                sel, rect = self._selected, self._drag_cur
                self._selected = None; self._drag_start = None
                self._drag_cur = None; self._resize_handle = None
                self.update()
                self.image_drag_done.emit(sel, rect)
            else:
                self._drag_start = None; self._resize_handle = None
                self.update()
        elif self._mode == "text":
            if self._text_sel and self._text_drag_cur_wr:
                span, wr = self._text_sel, self._text_drag_cur_wr
                self._text_sel = None; self._text_drag_start = None
                self._text_drag_cur_wr = None
                self.update()
                self.text_drag_done.emit(span, wr[0], wr[3])

    def contextMenuEvent(self, event):
        if self._mode == "text":
            self._text_context_menu(event); return
        if self._mode == "select":
            menu = QMenu(self)
            a = menu.addAction("⧉  Kopyala\tCtrl+C")
            a.setEnabled(bool(self._sel_highlight))
            a.triggered.connect(lambda: self.copy_requested.emit("selection", None))
            menu.addAction("Sayfadaki tüm metni seç\tCtrl+A").triggered.connect(
                lambda: self.copy_requested.emit("page", None))
            menu.exec(event.globalPos()); return
        if self._mode != "image":
            return
        hit = self._image_at(event.pos().x(), event.pos().y())
        if not hit:
            return
        self._selected = hit; self.update()
        menu = QMenu(self)
        items = [("⇤  Sola hizala", "left"), ("↔  Yatay ortala", "hcenter"), ("⇥  Sağa hizala", "right"),
                 None,
                 ("⤒  Üste hizala", "top"), ("↕  Dikey ortala", "vcenter"), ("⤓  Alta hizala", "bottom")]
        for it in items:
            if it is None:
                menu.addSeparator(); continue
            label, key = it
            menu.addAction(label).triggered.connect(
                lambda _=False, k=key, img=hit: self.image_align_req.emit(img, k))
        menu.addSeparator()
        menu.addAction("🗑  Sil").triggered.connect(lambda: self.image_delete_req.emit(hit))
        menu.exec(event.globalPos())

    def _text_context_menu(self, event):
        span = self._span_at(event.pos().x(), event.pos().y())
        menu = QMenu(self)
        if span:
            self._text_sel = span; self._text_drag_start = None; self.update()
            preview = span["text"].replace("\xa0", " ").strip()
            preview = preview if len(preview) <= 30 else preview[:29] + "…"
            menu.addAction(f"⧉  Kopyala  \"{preview}\"\tCtrl+C").triggered.connect(
                lambda: self.copy_requested.emit("span", span))
            menu.addAction("Satırın tamamını kopyala").triggered.connect(
                lambda: self.copy_requested.emit("line", span))
            menu.addSeparator()
        menu.addAction("Sayfadaki tüm metni kopyala").triggered.connect(
            lambda: self.copy_requested.emit("page", None))
        menu.exec(event.globalPos())

    def keyPressEvent(self, event):
        if self._mode == "image" and self._selected:
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.image_delete_req.emit(self._selected)
                self._selected = None; self.update(); return
        super().keyPressEvent(event)

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._mode in ("select", "erase"):
            if self._mode == "select" and self._sel_highlight:
                for x0, y0, x1, y1 in self._sel_highlight:
                    p.fillRect(QRectF(x0 - 1, y0, x1 - x0 + 2, y1 - y0), QColor(56, 132, 255, 70))
            if self._sel_start and self._sel_cur:
                a, b = self._sel_start, self._sel_cur
                r = QRectF(min(a.x(), b.x()), min(a.y(), b.y()),
                           abs(b.x() - a.x()), abs(b.y() - a.y()))
                if self._mode == "select":
                    p.fillRect(r, QColor(56, 132, 255, 45))
                    p.setPen(QPen(QColor("#3884ff"), 1))
                else:  # erase
                    p.fillRect(r, QColor(239, 68, 68, 40))
                    p.setPen(QPen(QColor("#ef4444"), 1, Qt.PenStyle.DashLine))
                p.drawRect(r)
            p.end(); return
        if self._mode == "text":
            if self._text_sel:
                wr = self._text_drag_cur_wr or self._text_sel.get("widget_rect")
                if wr:
                    x0, y0, x1, y1 = wr
                    r = QRectF(x0, y0, x1-x0, y1-y0)
                    if self._text_drag_cur_wr:
                        p.fillRect(r, QColor(99, 102, 241, 60))
                        p.setPen(QPen(QColor("#6366f1"), 2))
                    else:
                        p.setPen(QPen(QColor("#6366f1"), 1.5, Qt.PenStyle.DashLine))
                    p.drawRect(r)
            p.end(); return
        if self._mode != "image":
            p.end(); return
        dash = QPen(QColor("#6366f1"), 1.5, Qt.PenStyle.DashLine)
        for img in self._images:
            if img is not self._selected:
                self._draw_rect(p, img["widget_rect"], dash, None)
        if self._selected:
            rect = self._drag_cur or self._selected["widget_rect"]
            self._draw_rect(p, rect, QPen(QColor("#f59e0b"), 2), QColor(245, 158, 11, 30))
            self._draw_handles(p, rect)
        if self._drag_cur and self._guides:
            p.setPen(QPen(QColor("#ec4899"), 1))
            for kind, v in self._guides:
                if kind == "v":
                    p.drawLine(QPoint(int(v), 0), QPoint(int(v), self.height()))
                else:
                    p.drawLine(QPoint(0, int(v)), QPoint(self.width(), int(v)))
        p.end()

    # ── Yardımcılar ──────────────────────────────────────────────────────────

    def _span_at(self, x, y):
        for s in self._text_spans:
            wx0, wy0, wx1, wy1 = s["widget_rect"]
            if wx0-3 <= x <= wx1+3 and wy0-3 <= y <= wy1+3:
                return s
        return None

    def _image_at(self, x, y):
        for img in self._images:
            wx0, wy0, wx1, wy1 = img["widget_rect"]
            if wx0 <= x <= wx1 and wy0 <= y <= wy1:
                return img
        return None

    def _handle_positions(self, wr):
        x0, y0, x1, y1 = wr
        mx, my = (x0+x1)/2, (y0+y1)/2
        return {"nw":(x0,y0),"n":(mx,y0),"ne":(x1,y0),
                "w":(x0,my),              "e":(x1,my),
                "sw":(x0,y1),"s":(mx,y1),"se":(x1,y1)}

    def _handle_at(self, x, y):
        if not self._selected:
            return None
        wr = self._drag_cur or self._selected["widget_rect"]
        for name, (hx, hy) in self._handle_positions(wr).items():
            if abs(x-hx) <= 7 and abs(y-hy) <= 7:
                return name
        return None

    # ── Hizalama / yapışma ───────────────────────────────────────────────────

    def _snap_targets(self):
        """Sayfa kenar/orta çizgileri + metin blokları + diğer resimlerin kenar ve merkezleri"""
        xs, ys = list(self._snap_xs), list(self._snap_ys)
        for img in self._images:
            if img is self._selected:
                continue
            x0, y0, x1, y1 = img["widget_rect"]
            xs += [x0, (x0 + x1) / 2, x1]
            ys += [y0, (y0 + y1) / 2, y1]
        return xs, ys

    def _nearest(self, values, targets):
        """values içinden bir değerin SNAP_PX içinde kalan en yakın hedefi → (kaydırma, hedef)"""
        best = None
        for v in values:
            for t in targets:
                d = t - v
                if abs(d) <= self.SNAP_PX and (best is None or abs(d) < abs(best[0])):
                    best = (d, t)
        return best

    def _snap_edge(self, v, targets, kind):
        hit = self._nearest((v,), targets)
        if not hit:
            return v
        self._guides.append((kind, hit[1]))
        return hit[1]

    def _snap_move(self, rect, snap: bool):
        self._guides = []
        if not snap:
            return rect
        x0, y0, x1, y1 = rect
        xs, ys = self._snap_targets()
        bx = self._nearest((x0, (x0 + x1) / 2, x1), xs)
        if bx:
            x0 += bx[0]; x1 += bx[0]; self._guides.append(("v", bx[1]))
        by = self._nearest((y0, (y0 + y1) / 2, y1), ys)
        if by:
            y0 += by[0]; y1 += by[0]; self._guides.append(("h", by[1]))
        return (x0, y0, x1, y1)

    def _compute_resize(self, pos, snap: bool = True, keep_ratio: bool = True):
        dx, dy = pos.x()-self._drag_start.x(), pos.y()-self._drag_start.y()
        ox0, oy0, ox1, oy1 = self._drag_orig
        MIN = 20
        x0, y0, x1, y1 = ox0, oy0, ox1, oy1
        h = self._resize_handle
        if "n" in h: y0 = oy0+dy
        if "s" in h: y1 = oy1+dy
        if "w" in h: x0 = ox0+dx
        if "e" in h: x1 = ox1+dx

        self._guides = []
        if snap:
            xs, ys = self._snap_targets()
            if "w" in h: x0 = self._snap_edge(x0, xs, "v")
            if "e" in h: x1 = self._snap_edge(x1, xs, "v")
            if "n" in h: y0 = self._snap_edge(y0, ys, "h")
            if "s" in h: y1 = self._snap_edge(y1, ys, "h")

        if "n" in h: y0 = min(y0, oy1-MIN)
        if "s" in h: y1 = max(y1, oy0+MIN)
        if "w" in h: x0 = min(x0, ox1-MIN)
        if "e" in h: x1 = max(x1, ox0+MIN)

        # Köşe tutamacı → en/boy oranı korunur (logolar basıklaşmasın). Hangi
        # boyut daha çok değiştiyse o belirleyici; diğer eksenin kılavuzu geçersiz olur.
        if keep_ratio and len(h) == 2:
            ow, oh = ox1-ox0, oy1-oy0
            w, hh = x1-x0, y1-y0
            if abs(w/ow - 1) >= abs(hh/oh - 1):
                hh = w * oh / ow
                self._guides = [g for g in self._guides if g[0] == "v"]
            else:
                w = hh * ow / oh
                self._guides = [g for g in self._guides if g[0] == "h"]
            if "w" in h: x0 = x1 - w
            else:        x1 = x0 + w
            if "n" in h: y0 = y1 - hh
            else:        y1 = y0 + hh
        return (x0, y0, x1, y1)

    def _update_cursor(self, x, y):
        handle = self._handle_at(x, y) if self._selected else None
        if handle:
            self.setCursor(self._HANDLE_CURSORS[handle])
        elif self._image_at(x, y):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _draw_rect(self, p, wr, pen, fill):
        x0, y0, x1, y1 = wr
        r = QRectF(x0, y0, x1-x0, y1-y0)
        if fill:
            p.fillRect(r, fill)
        p.setPen(pen); p.drawRect(r)

    def _draw_handles(self, p, wr):
        p.setPen(QPen(QColor("#1e1e2e"), 1))
        p.setBrush(QBrush(QColor("#f59e0b")))
        for hx, hy in self._handle_positions(wr).values():
            p.drawRect(QRectF(hx-5, hy-5, 10, 10))


# ── Küçük resim (thumbnail) paneli ───────────────────────────────────────────

class ThumbnailWidget(QListWidget):
    page_selected = pyqtSignal(int)
    THUMB_W, THUMB_H = 108, 153

    def __init__(self):
        super().__init__()
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(self.THUMB_W, self.THUMB_H))
        self.setSpacing(4)
        self.setMovement(QListWidget.Movement.Static)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedWidth(142)
        self.setUniformItemSizes(True)
        self.setStyleSheet("""
            QListWidget {
                background: #13131f;
                border: none;
                padding-top: 6px;
                outline: none;
            }
            QListWidget::item {
                color: #585b70;
                padding: 3px;
                border-radius: 4px;
                font-size: 10px;
                border: 1px solid transparent;
            }
            QListWidget::item:selected {
                background: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #89b4fa;
            }
            QListWidget::item:hover:!selected {
                background: #1a1a2e;
            }
        """)
        self.itemClicked.connect(lambda item: self.page_selected.emit(self.row(item)))

    def load(self, render_fn, page_count: int):
        self.clear()
        for i in range(page_count):
            self._add_thumb(render_fn, i)

    def refresh_page(self, page_num: int, render_fn):
        if 0 <= page_num < self.count():
            try:
                png = render_fn(page_num, 0.2)
                self.item(page_num).setIcon(QIcon(QPixmap.fromImage(self._scale(png))))
            except Exception:
                pass

    def set_current(self, page_num: int):
        if 0 <= page_num < self.count():
            self.blockSignals(True)
            self.setCurrentRow(page_num)
            self.scrollToItem(self.item(page_num), QListWidget.ScrollHint.EnsureVisible)
            self.blockSignals(False)

    def _add_thumb(self, render_fn, i: int):
        try:
            png = render_fn(i, 0.2)
            icon = QIcon(QPixmap.fromImage(self._scale(png)))
        except Exception:
            icon = QIcon()
        item = QListWidgetItem(icon, str(i + 1))
        item.setSizeHint(QSize(self.THUMB_W + 20, self.THUMB_H + 26))
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.addItem(item)

    def _scale(self, png: bytes) -> QImage:
        return QImage.fromData(png).scaled(
            self.THUMB_W, self.THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )


# ── Ctrl+scroll ile zoom destekli scroll area ─────────────────────────────────

class _ZoomScrollArea(QScrollArea):
    ctrl_wheel = pyqtSignal(int)  # +1 / -1

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.ctrl_wheel.emit(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
        else:
            super().wheelEvent(event)


# ── Ana görüntüleyici widget ──────────────────────────────────────────────────

class PDFViewerWidget(QWidget):
    edit_requested   = pyqtSignal(float, float, int)
    text_drag_done   = pyqtSignal(dict, float, float, int)
    image_drag_done  = pyqtSignal(dict, tuple, int)
    image_delete_req = pyqtSignal(dict, int)
    text_select_done = pyqtSignal(tuple, int)
    area_erase_done  = pyqtSignal(tuple, int)
    image_align_req  = pyqtSignal(dict, str, int)
    copy_requested   = pyqtSignal(str, object, int)
    ctrl_scroll      = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.zoom = 1.5
        self._page_labels: list[PageLabel] = []
        self._wrappers:    list[QWidget]   = []
        self._mode = "text"

        self._scroll = _ZoomScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: #252535; }")
        self._scroll.ctrl_wheel.connect(self.ctrl_scroll)

        self._container = QWidget()
        self._container.setStyleSheet("background: #252535;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(20)
        self._layout.setContentsMargins(24, 24, 24, 24)

        self._scroll.setWidget(self._container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

    # ── Sayfa yükleme ─────────────────────────────────────────────────────────

    def load_pages(self, render_fn, page_count: int, images_fn=None):
        for w in self._wrappers:
            self._layout.removeWidget(w)
            w.deleteLater()
        self._page_labels.clear()
        self._wrappers.clear()

        for i in range(page_count):
            pixmap = self._to_pixmap(render_fn(i, self.zoom))
            lbl = PageLabel()
            lbl.setPixmap(pixmap)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            lbl.setFixedSize(pixmap.size())
            lbl.set_mode(self._mode)
            if images_fn:
                lbl.set_images(images_fn(i), self.zoom)

            wrapper = QWidget()
            wrapper.setStyleSheet("background: white;")
            wl = QVBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.addWidget(lbl)

            p = i
            lbl.text_edit_requested.connect(lambda x, y, pg=p: self.edit_requested.emit(x, y, pg))
            lbl.text_drag_done.connect(lambda s, wx, wy, pg=p: self.text_drag_done.emit(s, wx, wy, pg))
            lbl.image_drag_done.connect(lambda img, wr, pg=p: self.image_drag_done.emit(img, wr, pg))
            lbl.image_delete_req.connect(lambda img, pg=p: self.image_delete_req.emit(img, pg))
            lbl.text_select_done.connect(lambda wr, pg=p: self.text_select_done.emit(wr, pg))
            lbl.area_erase_done.connect(lambda wr, pg=p: self.area_erase_done.emit(wr, pg))
            lbl.image_align_req.connect(lambda img, k, pg=p: self.image_align_req.emit(img, k, pg))
            lbl.copy_requested.connect(lambda k, s, pg=p: self.copy_requested.emit(k, s, pg))

            self._layout.addWidget(wrapper, alignment=Qt.AlignmentFlag.AlignHCenter)
            self._page_labels.append(lbl)
            self._wrappers.append(wrapper)

    def refresh_page(self, page_num: int, render_fn, images=None):
        if page_num >= len(self._page_labels):
            return
        lbl = self._page_labels[page_num]
        pixmap = self._to_pixmap(render_fn(page_num, self.zoom))
        lbl.setPixmap(pixmap)
        lbl.setFixedSize(pixmap.size())
        if images is not None:
            lbl.set_images(images, self.zoom)

    def set_mode(self, mode: str):
        self._mode = mode
        for lbl in self._page_labels:
            lbl.set_mode(mode)

    def set_zoom(self, zoom: float, render_fn, page_count: int, images_fn=None):
        self.zoom = zoom
        self.load_pages(render_fn, page_count, images_fn)

    def get_page_label(self, page_num: int) -> "PageLabel | None":
        return self._page_labels[page_num] if page_num < len(self._page_labels) else None

    # ── Navigasyon yardımcıları ───────────────────────────────────────────────

    def scroll_to_page(self, page_num: int):
        if 0 <= page_num < len(self._wrappers):
            self._scroll.ensureWidgetVisible(self._wrappers[page_num], 0, 20)

    def visible_page(self) -> int:
        if not self._wrappers:
            return 0
        sv = self._scroll.verticalScrollBar().value()
        for i, w in enumerate(self._wrappers):
            if w.pos().y() + w.height() > sv:
                return i
        return len(self._wrappers) - 1

    def selected_span(self) -> "tuple[int, dict] | None":
        """Metin modunda tek tıkla seçili span → (sayfa, span)"""
        for i, lbl in enumerate(self._page_labels):
            s = lbl.get_text_selection()
            if s:
                return i, s
        return None

    def center_page(self) -> int:
        """Ekranın dikey ortasındaki sayfa — kullanıcının o an baktığı sayfa"""
        if not self._wrappers:
            return 0
        mid = self._scroll.verticalScrollBar().value() + self._scroll.viewport().height() / 2
        for i, w in enumerate(self._wrappers):
            if w.pos().y() + w.height() + self._layout.spacing() / 2 > mid:
                return i
        return len(self._wrappers) - 1

    def _to_pixmap(self, data: bytes) -> QPixmap:
        return QPixmap.fromImage(QImage.fromData(data))
