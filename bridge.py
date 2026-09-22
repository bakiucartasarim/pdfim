"""JS ↔ Python köprüsü — pywebview js_api olarak arayüze açılır.

Masaüstünde (app.py) her public metot `window.pywebview.api.<ad>(...)` ile, webde (server.py)
`POST /api/<ad>` ile çağrılır. pywebview public nitelikleri de dışarı açtığı için iç durum `_` ile
başlayan adlarda tutulur.

web=True iken dosya pencereleri ve Windows panosu yoktur: dosyalar yüklenir/indirilir, pano
tarayıcıdadır (metin ve resim JS'ten parametre olarak gelir).

Koordinatlar her zaman PDF noktası (pt, 1/72 inç) cinsindendir; ekran pikseline çevirmek
arayüzün işi. Böylece yakınlaştırma Python tarafını hiç ilgilendirmez.
"""

import functools
import json
import os
import tempfile
import threading

import fitz

import fonts

from editor import PDFEditor

try:                        # masaüstüne özgü: webde (Linux sunucu) yüklü değil / çalışmaz
    import webview
    import clipboard
except (ImportError, AttributeError, OSError):
    webview = clipboard = None

MAX_UNDO = 20
MAX_RECENT = 10
MAX_RENDER_PIXELS = 40_000_000   # ≈ 160 MB RGBA; 4K ekranda A4 %400'ün rahatça üstünde
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PDFim")
_RECENT_PATH = os.path.join(APPDATA_DIR, "recent.json")
_PDF_TYPES = ("PDF dosyaları (*.pdf)",)
_IMAGE_TYPES = ("Resim dosyaları (*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff)",)
_SPAN_KEYS = ("text", "origin", "size", "color", "font", "flags")
# Yoğun datasheet sayfalarında binlerce parça aynı birkaç fontu kullanır; eşleştirme her
# seferinde yüzlerce sistem fontunu taradığı için sonuç ad başına bir kez hesaplanır
_match_family = functools.lru_cache(maxsize=None)(fonts.match_family)


class DocState:
    """Köprü ile sayfa sunucusunun paylaştığı durum.

    Sayfa sürümü "gen.rev": gen belge her baştan yüklendiğinde (aç, geri al) artar, rev o
    sayfa her düzenlendiğinde. Sürüm sayfa URL'sine eklenir; yalnız değişen sayfanın
    görüntüsü yeniden istenir, diğerleri tarayıcı önbelleğinden gelir.
    """

    def __init__(self):
        self.editor = PDFEditor()
        self.lock = threading.RLock()
        self.gen = 0
        self.page_revs: list[int] = []

    def reset_versions(self):
        self.gen += 1
        self.page_revs = [0] * self.editor.page_count()

    def version(self, page: int) -> str:
        return f"{self.gen}.{self.page_revs[page]}"

    def render(self, page: int, scale: float, version: str) -> bytes | None:
        """Sayfa PNG'si; sürüm eskiyse ya da sayfa yoksa None. Kilit içinde: MuPDF aynı
        belgeye iki iş parçacığından aynı anda dokunulmasına dayanıklı değil."""
        with self.lock:
            ed = self.editor
            if not ed.doc or not 0 <= page < ed.page_count() or version != self.version(page):
                return None
            # Piksel sayısı sınırı: A0 çizim 8x ölçekte ~26000 px genişlik, tek istekte GB'larca bellek
            r = ed.doc[page].rect
            scale = min(scale, (MAX_RENDER_PIXELS / max(1.0, r.width * r.height)) ** 0.5)
            return ed.render_page(page, scale)


class Api:
    def __init__(self, state: DocState, on_doc_changed=None, web: bool = False, max_undo: int = MAX_UNDO):
        self._state = state
        self._web = web
        self._max_undo = max_undo
        self._window = None                       # webview.Window (yalnız masaüstü)
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []
        self._recent: list[str] = [] if web else _load_recent()
        self._on_doc_changed = on_doc_changed   # sayfa önbelleğini temizlemek için
        # PDFim içinden kopyalanan son metin ve kaynağının biçimi: yapıştırırken aynı
        # metin panodaysa biçimiyle yapıştırılır (v1 ile aynı davranış)
        self._last_copied = ""
        self._last_style: dict | None = None

    def _attach(self, window: "webview.Window"):
        self._window = window

    @property
    def _ed(self) -> PDFEditor:
        return self._state.editor

    # ── Durum ────────────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        with self._state.lock:
            ed = self._ed
            if not ed.doc:
                return {"open": False, "recent": self._recent}
            return {
                "open": True,
                "path": ed.path,
                "name": os.path.basename(ed.path) or "Adsız.pdf",
                "gen": self._state.gen,
                "versions": [self._state.version(i) for i in range(ed.page_count())],
                "modified": ed.modified,
                "canUndo": bool(self._undo),
                "canRedo": bool(self._redo),
                "pages": [[p.rect.width, p.rect.height] for p in ed.doc],
                "recent": self._recent,
            }

    def _reloaded(self):
        """Belge baştan yüklendi (aç / geri al / yinele): tüm sürümler yenilenir."""
        self._state.reset_versions()
        if self._on_doc_changed:
            self._on_doc_changed()
        self._update_title()

    def _update_title(self):
        if not self._window:
            return
        ed = self._ed
        if ed.doc:
            star = "• " if ed.modified else ""
            self._window.set_title(f"{star}{os.path.basename(ed.path) or 'Adsız'} — PDFim")
        else:
            self._window.set_title("PDFim")

    def _mutate(self, page: int, fn, *args) -> dict:
        """Belgeyi değiştiren her işlem buradan geçer: önce geri alma kopyası, başarısızsa
        kopya geri atılır. Başarılıysa yalnız o sayfanın sürümü artar."""
        with self._state.lock:
            ed = self._ed
            if not ed.doc or not 0 <= page < ed.page_count():
                return {"ok": False, "error": "Açık belge yok."}
            self._snapshot()
            ed.last_error = ""
            try:
                ok = fn(*args)
            except Exception as e:
                ok, ed.last_error = False, str(e)
            if not ok:
                self._undo.pop()
                return {"ok": False, "error": ed.last_error or "İşlem uygulanamadı."}
            ed.modified = True
            self._state.page_revs[page] += 1
        self._update_title()
        return {"ok": True, "state": self.get_state()}

    # ── Dosya ────────────────────────────────────────────────────────────────

    def open_dialog(self) -> dict | None:
        """Dosya seçtirip açar. Kullanıcı vazgeçerse None."""
        if not self._confirm_discard():
            return None
        start = os.path.dirname(self._ed.path) if self._ed.path else ""
        paths = self._window.create_file_dialog(
            webview.FileDialog.OPEN, directory=start, file_types=_PDF_TYPES)
        if not paths:
            return None
        return self.open_path(paths[0])

    def open_path(self, path: str, password: str | None = None) -> dict:
        # Ayrı bir editörde dene: editor.open() önce mevcut belgeyi kapatır, yanlış parola ya da
        # bozuk dosyada açık (belki kaydedilmemiş) belge kaybolmasın
        new = PDFEditor()
        if not new.open(path, password):
            return {"ok": False, "error": new.last_error,
                    "needsPassword": new.needs_password, "path": path}
        with self._state.lock:
            self._ed.close()
            self._state.editor = new
            self._undo.clear()
            self._redo.clear()
            self._reloaded()
        self._add_recent(new.path)
        return {"ok": True, "state": self.get_state()}

    def save(self) -> dict:
        ed = self._ed
        if not ed.doc:
            return {"ok": False, "error": "Açık belge yok."}
        if not ed.path:
            return self.save_as()
        with self._state.lock:
            ok = ed.save()
        self._update_title()
        return {"ok": ok, "error": ed.last_error, "state": self.get_state()}

    def save_as(self) -> dict | None:
        ed = self._ed
        if not ed.doc:
            return {"ok": False, "error": "Açık belge yok."}
        name = os.path.basename(ed.path) or "Adsız.pdf"
        target = self._window.create_file_dialog(
            webview.FileDialog.SAVE, directory=os.path.dirname(ed.path),
            save_filename=name, file_types=_PDF_TYPES)
        if not target:
            return None
        target = target if isinstance(target, str) else target[0]
        if not target.lower().endswith(".pdf"):
            target += ".pdf"
        with self._state.lock:
            ok = ed.save(target)
        if ok:
            self._add_recent(ed.path)
        self._update_title()
        return {"ok": ok, "error": ed.last_error, "state": self.get_state()}

    def _export(self) -> tuple[bytes, str] | None:
        """Web "İndir": belgenin tamamı (masaüstündeki kayıtla aynı ayarlar) + dosya adı."""
        with self._state.lock:
            ed = self._ed
            if not ed.doc:
                return None
            data = ed.doc.tobytes(garbage=3, deflate=True)
            ed.modified = False
            return data, os.path.basename(ed.path) or "belge.pdf"

    def _add_recent(self, path: str):
        if self._web:
            return
        self._recent = ([path] + [p for p in self._recent if p != path])[:MAX_RECENT]
        try:
            os.makedirs(APPDATA_DIR, exist_ok=True)
            with open(_RECENT_PATH, "w", encoding="utf-8") as f:
                json.dump(self._recent, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ── Sayfa katmanı (tıklanabilir metin ve resim kutuları) ─────────────────

    def page_layer(self, page: int) -> dict | None:
        """Bir sayfanın metin parçaları, resimleri ve hizalama kılavuzları."""
        with self._state.lock:
            ed = self._ed
            if not ed.doc or not 0 <= page < ed.page_count():
                return None
            p = ed.doc[page]
            spans = []
            for block in p.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    for s in line["spans"]:
                        if not s["text"].strip():
                            continue
                        spans.append({**{k: s[k] for k in _SPAN_KEYS},
                                      "rect": tuple(s["bbox"]),
                                      # Düzenleme kutusunda aynı fontla önizleme için
                                      "family": _match_family(s["font"])})
            images = ed.get_images(page)
            _stack_order(p, spans, images)
            # Resim hizalama kılavuzları: sayfa kenarları + ortası, metin alanı, metin blokları
            pr = p.rect
            cx0, cy0, cx1, cy1 = ed.content_rect(page)
            xs = [0, pr.width / 2, pr.width, cx0, cx1]
            ys = [0, pr.height / 2, pr.height, cy0, cy1]
            for bx0, by0, bx1, by1 in ed.text_block_rects(page):
                xs += [bx0, bx1]
                ys += [by0, by1]
            return {"version": self._state.version(page), "spans": spans,
                    "images": images, "snapX": xs, "snapY": ys,
                    "content": [cx0, cy0, cx1, cy1]}

    # ── Metin ────────────────────────────────────────────────────────────────

    def replace_text(self, page: int, span: dict, text: str, style: dict | None) -> dict:
        if text == span["text"] and not style:
            return {"ok": True, "state": self.get_state()}   # değişiklik yok
        if not text.strip():
            return {"ok": False, "error": "Boş metin uygulanmadı — silmek için 'Alan Sil' aracını kullanın."}
        return self._mutate(page, self._ed.replace_text, page, span, text, style)

    def move_text(self, page: int, span: dict, x: float, y_base: float) -> dict:
        return self._mutate(page, self._ed.move_text_span, page, span, x, y_base)

    def insert_text(self, page: int, x: float, y_base: float, text: str, style: dict | None) -> dict:
        """Metin aracı: yeni yazı. style biçim çubuğundan (family/size/bold/italic/color)."""
        if not text.strip():
            return {"ok": False, "error": "Boş metin eklenmedi."}
        return self._mutate(page, self._ed.insert_new_text, page, (x, y_base), text, style)

    def system_fonts(self) -> list[str]:
        return sorted(fonts.system_fonts(), key=str.lower)

    # ── Kopyala / yapıştır ───────────────────────────────────────────────────

    def _copy(self, text: str, style: dict | None) -> dict:
        """Masaüstünde panoya yazar; webde metni döndürür, JS tarayıcı panosuna yazar."""
        if not text:
            return {"ok": False, "error": "Kopyalanacak metin yok."}
        if not self._web and not clipboard.set_text(text):
            return {"ok": False, "error": "Panoya yazılamadı — pano başka bir programda açık, biraz sonra tekrar deneyin."}
        self._last_copied, self._last_style = text, style
        return {"ok": True, "text": text}

    def select_text(self, page: int, rect: list) -> dict:
        """Metin Seç aracı: alandaki kelimeler → vurgu kutuları, metin panoya kopyalanır."""
        with self._state.lock:
            ed = self._ed
            txt, rects = ed.select_words(page, tuple(rect))
            style = ed.style_at(page, rects[0]) if rects else None
        result = self._copy(txt, style) if txt else {"ok": False, "error": "Seçilen alanda metin yok."}
        return {**result, "rects": [list(r) for r in rects]}

    def copy_text(self, kind: str, page: int, span: dict | None = None) -> dict:
        """kind: "span" (tıklanan parça) | "line" (satırın tamamı) | "page" (sayfanın tümü)"""
        with self._state.lock:
            ed = self._ed
            if not ed.doc:
                return {"ok": False, "error": "Açık belge yok."}
            style = {k: span[k] for k in ("font", "flags", "size", "color")} if span else None
            if kind == "span":
                txt = ed.clean_text(span["text"]).strip()
            elif kind == "line":
                txt = ed.line_text_at(page, span["rect"])
            else:
                txt, rects = ed.select_words(page, tuple(ed.doc[page].rect))
                style = ed.style_at(page, rects[0]) if rects else None
        return self._copy(txt, style)

    def clipboard_info(self, text: str | None = None, has_image: bool = False) -> dict:
        """Panoda ne var? Resim önceliklidir (Ekran Alıntısı Aracı çoğu zaman ikisini de koyar).
        Webde pano tarayıcıda okunur, içeriği parametre olarak gelir."""
        if self._web:
            if has_image:
                return {"kind": "image"}
            txt = text or ""
            if not txt.strip():
                return {"kind": None}
        else:
            if clipboard.has_image():
                return {"kind": "image"}
            txt = clipboard.get_text()
            if not txt.strip():
                return {"kind": None, "locked": clipboard.is_locked()}
        style = self._paste_style(txt)
        sp = {**PDFEditor.DEFAULT_TEXT_STYLE, **(style or {})}
        return {"kind": "text", "text": txt, "fromPdfim": style is not None,
                "size": sp["size"], "color": sp["color"],
                "family": fonts.match_family(sp["font"]) or "Arial",
                "bold": bool(sp.get("flags", 0) & 16)}

    def _paste_style(self, txt: str) -> dict | None:
        """PDFim'den kopyalandıysa kaynağın biçimi, dışarıdan geldiyse None (→ Arial 10)."""
        style = self._last_style if txt == self._last_copied else None
        if style:
            c = style.get("color", 0)
            lum = (0.299 * (c >> 16 & 255) + 0.587 * (c >> 8 & 255) + 0.114 * (c & 255)) / 255
            if lum > 0.85:
                # Koyu zemin üstündeki beyaz başlık (ör. mavi bant) beyaz sayfaya
                # yapıştırılınca görünmez oluyordu; font/punto/kalınlık korunur, renk siyah
                style = {**style, "color": 0x000000}
        return style

    def paste_text(self, page: int, x: float, y_base: float, text: str | None = None) -> dict:
        txt = text if self._web else clipboard.get_text()
        txt = txt or ""
        if not txt.strip():
            return {"ok": False, "error": "Panoda yapıştırılacak metin yok."}
        return self._mutate(page, self._ed.insert_new_text, page, (x, y_base), txt,
                            self._paste_style(txt))

    def paste_image(self, page: int, at: list | None = None, data: str | None = None) -> dict:
        """data: webde tarayıcı panosundaki resim (base64). Masaüstünde Windows panosundan."""
        png = _b64(data) if self._web else clipboard.get_image_png()
        if not png:
            return {"ok": False, "error": "Panodaki resim okunamadı."}
        return self._insert_image(page, png, at)

    def add_image_data(self, page: int, data: str) -> dict:
        """Web: kullanıcının seçtiği resim dosyası (base64)."""
        png = _b64(data)
        if not png:
            return {"ok": False, "error": "Resim okunamadı."}
        return self._insert_image(page, png, None)

    # ── Resim ────────────────────────────────────────────────────────────────

    def add_image(self, page: int) -> dict | None:
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=_IMAGE_TYPES)
        if not paths:
            return None
        try:
            with open(paths[0], "rb") as f:
                data = f.read()
        except OSError as e:
            return {"ok": False, "error": f"Resim okunamadı.\n({e})"}
        return self._insert_image(page, data, None)

    def _insert_image(self, page: int, data: bytes, at: list | None) -> dict:
        """at verilirse (sağ tık → yapıştır) resmin üst-sol köşesi oraya ve resim ekrandaki
        doğal boyutunda; verilmezse sayfanın ortasına. Dönüşte eklenen kutu ("rect") var,
        arayüz resmi seçili getirir."""
        try:
            pix = fitz.Pixmap(data)
            iw, ih = pix.width, pix.height
        except Exception:
            return {"ok": False, "error": "Resim okunamadı. Desteklenmeyen biçim olabilir."}
        with self._state.lock:
            ed = self._ed
            if not ed.doc:
                return {"ok": False, "error": "Açık belge yok."}
            pr = ed.doc[page].rect
            pw, ph = pr.width, pr.height
            cx0, _, cx1, _ = ed.content_rect(page)
        # Kutu resmin kendi en/boy oranında: seçim çerçevesi resimle örtüşsün
        w = min(iw * 0.75, cx1 - cx0) if at else min(cx1 - cx0, pw * 0.4)   # 96 dpi → 1 px = 0.75 pt
        h = w * ih / iw
        if h > ph * 0.4:
            h = ph * 0.4
            w = h * iw / ih
        if at:                                   # sayfa dışına taşmasın
            x0 = min(max(at[0], 0), pw - w)
            y0 = min(max(at[1], 0), ph - h)
        else:
            x0, y0 = (pw - w) / 2, (ph - h) / 2
        rect = (x0, y0, x0 + w, y0 + h)

        fd, tmp = tempfile.mkstemp(suffix=".png", prefix="pdfim_img_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            result = self._mutate(page, self._ed.insert_image_file, page, rect, tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if not result["ok"]:
            result["error"] = "Resim eklenemedi. Desteklenmeyen biçim olabilir."
        return {**result, "rect": list(rect)}

    def move_image(self, page: int, img: dict, rect: list) -> dict:
        return self._mutate(page, self._ed.move_image, page, img, tuple(rect))

    def delete_image(self, page: int, img: dict) -> dict:
        return self._mutate(page, self._ed.delete_image, page, img)

    def align_image(self, page: int, img: dict, how: str) -> dict:
        """Kenarlara hizalama metin alanına (kenar boşluklarına), ortalama sayfanın tam ortasına."""
        with self._state.lock:
            ed = self._ed
            if not ed.doc:
                return {"ok": False, "error": "Açık belge yok."}
            x0, y0, x1, y1 = img["rect"]
            w, h = x1 - x0, y1 - y0
            cx0, cy0, cx1, cy1 = ed.content_rect(page)
            pr = ed.doc[page].rect
        if how == "left":
            x0 = cx0
        elif how == "right":
            x0 = cx1 - w
        elif how == "hcenter":
            x0 = (pr.width - w) / 2
        elif how == "top":
            y0 = cy0
        elif how == "bottom":
            y0 = cy1 - h
        elif how == "vcenter":
            y0 = (pr.height - h) / 2
        result = self.move_image(page, img, [x0, y0, x0 + w, y0 + h])
        return {**result, "rect": [x0, y0, x0 + w, y0 + h]}

    # ── Alan sil ─────────────────────────────────────────────────────────────

    def erase_area(self, page: int, rect: list) -> dict:
        return self._mutate(page, self._ed.erase_area, page, tuple(rect))

    # ── Geri al / yinele ─────────────────────────────────────────────────────
    # Her düzenleme öncesi belgenin tamamının bayt kopyası alınır (v1 ile aynı yöntem).
    # Basit ve her işlem türü için doğru; bedeli 20 × dosya boyutu kadar bellek.

    def _snapshot(self):
        """_mutate çağırır, değişiklikten önce (kilit içinde)."""
        self._undo.append(self._ed.doc.tobytes())
        del self._undo[:-self._max_undo]
        self._redo.clear()

    def _restore(self, src: list, dst: list) -> dict:
        with self._state.lock:
            ed = self._ed
            if not src or not ed.doc:
                return self.get_state()
            dst.append(ed.doc.tobytes())
            ed.open_from_bytes(src.pop(), ed.path)
            self._reloaded()
            return self.get_state()

    def undo(self) -> dict:
        return self._restore(self._undo, self._redo)

    def redo(self) -> dict:
        return self._restore(self._redo, self._undo)

    # ── Pencere ──────────────────────────────────────────────────────────────

    def _confirm_discard(self) -> bool:
        """Kaydedilmemiş değişiklik varsa sorar. True → belge bırakılabilir (kapat / başkasını aç)."""
        ed = self._ed
        if not ed.doc or not ed.modified:
            return True
        return self._window.create_confirmation_dialog(
            "Kaydedilmemiş değişiklikler",
            f"{os.path.basename(ed.path) or 'Belge'} dosyasındaki değişiklikler kaydedilmedi.\n"
            "Kaydetmeden devam edilsin mi?")


def _b64(data: str | None) -> bytes | None:
    import base64
    import binascii
    if not data:
        return None
    try:
        return base64.b64decode(data.split(",", 1)[-1], validate=False)   # "data:image/png;base64," öneki olabilir
    except (binascii.Error, ValueError):
        return None


def _stack_order(page: fitz.Page, spans: list, images: list):
    """Üst üste binen metin ve resimlere çizim sırası ("z") ekler: tıklama, ekranda üstte
    görünene gitsin (paragrafın üstüne konmuş logo ↔ bant resminin üstündeki başlık).

    Yalnız bir resimle çakışan metinler hesaplanır; diğerlerinde çakışma olmadığı için
    sıranın önemi yok (yoğun datasheet sayfalarında binlerce parça var)."""
    for s in spans:
        s["z"] = 0
    for img in images:
        img["z"] = 0
    if not images:
        return
    rects = [fitz.Rect(img["rect"]) for img in images]
    overlapping = [s for s in spans if any(r.intersects(s["rect"]) for r in rects)]
    if not overlapping:
        return
    try:
        log = page.get_bboxlog()
    except Exception:
        return
    for img, r in zip(images, rects):
        for n, (kind, bbox) in enumerate(log):
            if "image" in kind and abs(bbox[0] - r.x0) < 1 and abs(bbox[1] - r.y0) < 1 \
                    and abs(bbox[2] - r.x1) < 1 and abs(bbox[3] - r.y1) < 1:
                img["z"] = n            # aynı resim birden çok kez çizildiyse sonuncusu
    for s in overlapping:
        cx, cy = (s["rect"][0] + s["rect"][2]) / 2, (s["rect"][1] + s["rect"][3]) / 2
        for n, (kind, bbox) in enumerate(log):
            if "text" in kind and bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]:
                s["z"] = n


def _load_recent() -> list:
    try:
        with open(_RECENT_PATH, encoding="utf-8") as f:
            return [p for p in json.load(f) if os.path.exists(p)][:MAX_RECENT]
    except (OSError, ValueError):
        return []
