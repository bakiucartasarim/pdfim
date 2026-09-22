"""PDF metin + resim düzenleme engine — PyMuPDF"""

import os
import re
import tempfile
import fitz  # PyMuPDF

import fonts

_FONTS_DIR = "C:/Windows/Fonts"

# Bold/italic kombinasyonuna göre fallback Arial dosyaları
_ARIAL_VARIANTS = {
    (False, False): "arial.ttf",
    (True,  False): "arialbd.ttf",
    (False, True):  "ariali.ttf",
    (True,  True):  "arialbi.ttf",
}


class PDFEditor:
    def __init__(self):
        self.doc: fitz.Document | None = None
        self.path: str = ""
        self.modified = False
        self._font_cache: dict = {}      # span_font_name → {fontfile, fontname}
        self._font_tmpfiles: list = []   # temizlenecek geçici dosyalar
        self._font_objs: dict = {}       # fontfile → fitz.Font (glif kontrolü / genişlik ölçümü)
        self.last_error: str = ""        # son open/save hatasının kullanıcıya gösterilecek açıklaması
        self.needs_password = False

    def open(self, path: str, password: str | None = None) -> bool:
        """Dosyayı belleğe okuyup açar.

        Dosyadan doğrudan açmak (fitz.open(path)) dosyayı kilitli tutar; bu da
        aynı dosyanın üzerine kaydetmeyi ve başka programın dosyayı açmasını
        engelliyordu. Bellekten açınca diskteki dosyayla bağ kalmaz.
        """
        self.close()
        self.last_error = ""
        self.needs_password = False
        try:
            with open(path, "rb") as f:
                data = f.read()
            doc = fitz.open(stream=data, filetype="pdf")
        except PermissionError:
            self.last_error = "Dosyaya erişim izni yok ya da başka bir program dosyayı kilitlemiş."
            return False
        except Exception as e:
            self.last_error = f"Dosya okunamadı veya geçerli bir PDF değil.\n({e})"
            return False
        if doc.needs_pass and not doc.authenticate(password or ""):
            doc.close()
            self.needs_password = True
            self.last_error = "Dosya parola korumalı." if not password else "Parola hatalı."
            return False
        self.doc = doc
        self.path = os.path.abspath(path)
        self.modified = False
        self._font_cache = {}
        return True

    def open_from_bytes(self, data: bytes, original_path: str = "") -> bool:
        """Undo/redo snapshot'tan belgeyi geri yükle"""
        self.close()
        try:
            self.doc = fitz.open(stream=data, filetype="pdf")
            self.path = original_path
            self.modified = True
            self._font_cache = {}
            return True
        except Exception:
            return False

    def page_count(self) -> int:
        return len(self.doc) if self.doc else 0

    def render_page(self, page_num: int, zoom: float = 1.5) -> bytes:
        page = self.doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")

    def find_text_at(self, page_num: int, x: float, y: float, zoom: float = 1.5):
        page = self.doc[page_num]
        px, py = x / zoom, y / zoom
        for block in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    r = fitz.Rect(span["bbox"])
                    if r.x0 - 3 <= px <= r.x1 + 3 and r.y0 - 3 <= py <= r.y1 + 3:
                        return {
                            "text":   span["text"],
                            "rect":   span["bbox"],
                            "origin": span["origin"],   # taban çizgisi başlangıcı
                            "size":   span["size"],
                            "color":  span["color"],
                            "font":   span["font"],
                            "flags":  span["flags"],
                        }
        return None

    @staticmethod
    def clean_text(text: str) -> str:
        """Panoya gidecek metni temizle. PDFim'in yazdığı metinlerde boşluklar
        NBSP (\\xa0) olarak çıkıyor; Excel'e yapıştırınca sayılar sayı sayılmıyordu."""
        # U+00AD: Arial'in tire glifi geri okunurken "yumuşak tire" çıkıyor ("PX-300" → "PX300" olmasın)
        return text.replace("\xa0", " ").replace("­", "-")

    def select_words(self, page_num: int, pdf_rect: tuple) -> tuple[str, list]:
        """Bir dikdörtgenin içine düşen kelimeler → (okunabilir metin, kelime kutuları).

        Kelimenin merkezi seçim dikdörtgenindeyse alınır. Satırlar PDF'in iç
        blok/satır yapısına göre değil *ekrandaki yatay hizaya* göre kurulur:
        datasheet tablolarında her sütun ayrı bloktur, yapıya göre gruplayınca
        "Gerilim" ile "24 V" ayrı satırlara düşüyordu. Sütun boşlukları Tab olur —
        Excel'e yapıştırınca hücrelere dağılır. Kutular vurgulama için döner.
        """
        if not self.doc:
            return "", []
        page = self.doc[page_num]
        sel = fitz.Rect(pdf_rect)
        sel.normalize()

        words = []
        for x0, y0, x1, y1, word, *_ in page.get_text("words", flags=fitz.TEXT_PRESERVE_WHITESPACE):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if sel.x0 <= cx <= sel.x1 and sel.y0 <= cy <= sel.y1:
                words.append((x0, y0, x1, y1, word))
        if not words:
            return "", []

        # Dikey merkezi yakın kelimeler aynı satır (yükseklikten yarımından az fark)
        words.sort(key=lambda t: ((t[1] + t[3]) / 2, t[0]))
        rows: list[dict] = []
        for wd in words:
            cy, h = (wd[1] + wd[3]) / 2, wd[3] - wd[1]
            if rows and abs(cy - rows[-1]["cy"]) <= max(h, rows[-1]["h"]) * 0.5:
                rows[-1]["words"].append(wd)
            else:
                rows.append({"cy": cy, "h": h, "words": [wd]})

        lines, prev = [], None
        for row in rows:
            ws = sorted(row["words"], key=lambda t: t[0])
            parts = [ws[0][4]]
            for a, b in zip(ws, ws[1:]):
                # Kelime arası ~0.3 em; bir satır yüksekliğinden büyük boşluk = yeni sütun
                parts.append("\t" if b[0] - a[2] > row["h"] * 0.9 else " ")
                parts.append(b[4])
            if prev and row["cy"] - prev["cy"] > max(row["h"], prev["h"]) * 2.2:
                lines.append("")                 # paragraf arası boş satır
            lines.append("".join(parts))
            prev = row
        return self.clean_text("\n".join(lines).strip()), [w[:4] for w in words]

    def text_in_rect(self, page_num: int, pdf_rect: tuple) -> str:
        return self.select_words(page_num, pdf_rect)[0]

    def line_text_at(self, page_num: int, rect: tuple) -> str:
        """Span'in hizasındaki tüm satır, sayfa genişliğince (tablo satırı → Tab'lı hücreler)"""
        pr = self.doc[page_num].rect
        r = fitz.Rect(rect)
        return self.select_words(page_num, (pr.x0, r.y0, pr.x1, r.y1))[0]

    def page_text(self, page_num: int) -> str:
        return self.select_words(page_num, tuple(self.doc[page_num].rect))[0]

    # ── Metin işlemleri ───────────────────────────────────────────────────────

    def replace_text(self, page_num: int, span_info: dict, new_text: str,
                     style: dict | None = None) -> bool:
        """Span'i sil, yerine yaz. `style` (biçim toolbar'ından) verilmezse orijinal biçim.

        style: family (None = orijinal font), size, bold, italic, underline,
               color (0xRRGGBB), align ("left" | "center" | "right")
        Hizalama orijinal span kutusunun içinde yapılır: tablo hücresindeki sağa
        yaslı bir değer, yeni metin kısa/uzun da olsa sağ kenarında kalır.
        """
        if not self.doc:
            return False
        page = self.doc[page_num]
        rect = fitz.Rect(span_info["rect"])
        flags = span_info.get("flags", 0)
        st = {"family": None, "size": span_info["size"],
              "bold": bool(flags & 16), "italic": bool(flags & 2),
              "underline": False, "color": span_info["color"], "align": "left",
              **(style or {})}
        try:
            font_kw = self._resolve_font(page, span_info, st, new_text)
            size = st["size"]
            width = self._text_width(font_kw, new_text, size)
            ox, oy = span_info.get("origin") or (rect.x0, rect.y1 - 1)
            if st["align"] == "center":
                x = rect.x0 + (rect.width - width) / 2
            elif st["align"] == "right":
                x = rect.x1 - width
            else:
                x = ox
            color = self._int_to_rgb(st["color"])

            page.add_redact_annot(rect, fill=None)
            page.apply_redactions(images=0, graphics=0)
            page.insert_text((x, oy), new_text, fontsize=size, color=color, **font_kw)
            if st["underline"] and width > 0:
                uy = oy + size * 0.12
                page.draw_line((x, uy), (x + width, uy), color=color,
                               width=max(0.4, size * 0.06))
            self.modified = True
            return True
        except Exception as e:
            print(f"[replace_text] HATA: {e}")
            return False

    # ── Yapıştırma: yeni metin ────────────────────────────────────────────────

    DEFAULT_TEXT_STYLE = {"font": "Arial", "flags": 0, "size": 10.0, "color": 0x000000}

    def style_at(self, page_num: int, rect: tuple) -> dict | None:
        """Bir konumdaki metnin biçimi (font/flags/size/color) — kopyalanan metin
        kaynağındaki biçimle yapıştırılabilsin diye"""
        r = fitz.Rect(rect)
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        for block in self.doc[page_num].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for s in line["spans"]:
                    b = fitz.Rect(s["bbox"])
                    if b.x0 <= cx <= b.x1 and b.y0 <= cy <= b.y1:
                        return {k: s[k] for k in ("font", "flags", "size", "color")}
        return None

    def insert_new_text(self, page_num: int, origin: tuple, text: str,
                        style: dict | None = None) -> bool:
        """Sayfaya yeni metin yaz. origin: ilk satırın taban çizgisi başlangıcı (PDF pt).
        Çok satırlı metin alt alta yazılır; Tab'lar (tablodan kopya) boşluğa çevrilir."""
        if not self.doc or not text.strip():
            return False
        page = self.doc[page_num]
        sp = {**self.DEFAULT_TEXT_STYLE, **(style or {})}
        flags = sp.get("flags", 0)
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ").rstrip("\n")
        st = {"family": None, "size": sp["size"], "bold": bool(flags & 16),
              "italic": bool(flags & 2), "color": sp["color"]}
        try:
            font_kw = self._resolve_font(page, sp, st, text)
            page.insert_text(origin, text, fontsize=sp["size"], lineheight=1.25,
                             color=self._int_to_rgb(sp["color"]), **font_kw)
            self.modified = True
            return True
        except Exception as e:
            print(f"[insert_new_text] HATA: {e}")
            return False

    # ── Biçim: font seçimi ────────────────────────────────────────────────────

    def _resolve_font(self, page: fitz.Page, span_info: dict, st: dict, text: str) -> dict:
        """Aday fontları sırayla dene; metnin tüm karakterlerini içeren ilkini seç.

        Gömülü fontlar çoğu zaman *alt kümedir* (sadece belgede geçen harfler);
        yeni yazılan "µ" ya da "Ş" orada yoksa PDF'te boş kutu çıkar.
        """
        flags = span_info.get("flags", 0)
        orig_style = (bool(flags & 16), bool(flags & 2))
        b, i = st["bold"], st["italic"]
        candidates = []
        if st.get("family"):
            candidates.append(self._file_kwargs(fonts.font_file(st["family"], b, i)))
        else:
            if (b, i) == orig_style:                   # biçim değişmediyse gömülü orijinal font
                candidates.append(self._get_font_kwargs(page, span_info))
            family = fonts.match_family(span_info.get("font", ""))
            if family:
                candidates.append(self._file_kwargs(fonts.font_file(family, b, i)))
            candidates.append(self._find_system_font(span_info.get("font", ""), b, i))
        candidates.append(self._file_kwargs(os.path.join(_FONTS_DIR, _ARIAL_VARIANTS[(b, i)])))
        candidates = [c for c in candidates if c]
        for kw in candidates:
            if self._covers(kw, text):
                return kw
        return candidates[0] if candidates else {"fontname": "helv"}

    @staticmethod
    def _file_kwargs(path: str | None) -> dict | None:
        if not path or not os.path.exists(path):
            return None
        stem = re.sub(r"\W", "", os.path.splitext(os.path.basename(path))[0])
        return {"fontfile": path, "fontname": f"SYS_{stem}"}

    def _font_obj(self, kw: dict) -> fitz.Font:
        path = kw.get("fontfile")
        if not path:
            return fitz.Font(kw.get("fontname", "helv"))
        if path not in self._font_objs:
            self._font_objs[path] = fitz.Font(fontfile=path)
        return self._font_objs[path]

    def _covers(self, kw: dict, text: str) -> bool:
        try:
            font = self._font_obj(kw)
        except Exception:
            return False
        if not kw.get("fontfile"):                     # helv: sadece WinAnsi (Türkçe ş/ğ/İ yok)
            return all(c.isspace() or ord(c) < 256 for c in text)
        return all(c.isspace() or font.has_glyph(ord(c)) for c in text)

    def _text_width(self, kw: dict, text: str, size: float) -> float:
        try:
            return self._font_obj(kw).text_length(text, fontsize=size)
        except Exception:
            return fitz.get_text_length(text, "helv", size)

    def move_text_span(self, page_num: int, span_info: dict,
                       new_x: float, new_y_base: float) -> bool:
        if not self.doc:
            return False
        page = self.doc[page_num]
        rect = fitz.Rect(span_info["rect"])
        try:
            page.add_redact_annot(rect, fill=None)
            page.apply_redactions(images=0, graphics=0)
            page.insert_text(
                (new_x, new_y_base),
                span_info["text"],
                fontsize=span_info["size"],
                color=self._int_to_rgb(span_info["color"]),
                **self._get_font_kwargs(page, span_info),
            )
            self.modified = True
            return True
        except Exception as e:
            print(f"[move_text_span] HATA: {e}")
            return False

    # ── Resim işlemleri ───────────────────────────────────────────────────────

    def get_images(self, page_num: int) -> list:
        if not self.doc:
            return []
        page = self.doc[page_num]
        result, seen = [], set()
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                for r in page.get_image_rects(xref):
                    rect = (r.x0, r.y0, r.x1, r.y1)
                    # Aynı içerikli resimler farklı xref'lerde de aynı konumları döndürebiliyor
                    if any(d["rect"] == rect for d in result):
                        continue
                    result.append({"xref": xref, "rect": rect,
                                   "w": img[2], "h": img[3]})
            except Exception:
                continue
        return result

    def _remove_image(self, page: fitz.Page, rect: tuple):
        """Resmi sayfadan kaldır.

        IMAGE_REMOVE, redaksiyon alanına *değen* tüm resimleri siler. Tüm resim
        alanını verirsek kenarı kenarına hizalanmış komşu resimler de gider;
        bu yüzden sadece resmin merkezindeki 2x2 pt'lik bir noktayı hedefliyoruz.
        """
        r = fitz.Rect(rect)
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        page.add_redact_annot(fitz.Rect(cx - 1, cy - 1, cx + 1, cy + 1), fill=None)
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_REMOVE,
            graphics=0,
            text=fitz.PDF_REDACT_TEXT_NONE,   # resmin altındaki yazıya dokunma
        )

    def _image_bytes(self, xref: int) -> bytes:
        """Resmi, varsa şeffaflık maskesiyle (smask) birlikte PNG olarak döndür.

        extract_image()["image"] sadece ana resmi verir; şeffaf PNG logolar
        taşındıktan sonra siyah zeminli çıkıyordu.
        """
        info = self.doc.extract_image(xref)
        smask = info.get("smask", 0)
        if not smask:
            return info["image"]
        try:
            base = fitz.Pixmap(self.doc, xref)
            if base.n - base.alpha >= 4:          # CMYK → PNG desteklemez
                base = fitz.Pixmap(fitz.csRGB, base)
            return fitz.Pixmap(base, fitz.Pixmap(self.doc, smask)).tobytes("png")
        except Exception:
            return info["image"]

    def delete_image(self, page_num: int, img_info: dict) -> bool:
        if not self.doc:
            return False
        self._remove_image(self.doc[page_num], img_info["rect"])
        self.modified = True
        return True

    def move_image(self, page_num: int, img_info: dict, new_pdf_rect: tuple) -> bool:
        if not self.doc:
            return False
        page = self.doc[page_num]
        try:
            img_bytes = self._image_bytes(img_info["xref"])
        except Exception:
            return False
        self._remove_image(page, img_info["rect"])
        # keep_proportion=False: resim ekranda bırakılan kutuyu birebir doldurur.
        # True iken kutunun ortasına küçültülüyor, hizalama kayıyordu.
        # (Oranı korumak artık köşe tutamaçlarının işi — bkz. viewer._compute_resize)
        page.insert_image(fitz.Rect(new_pdf_rect), stream=img_bytes, keep_proportion=False)
        self.modified = True
        return True

    def erase_area(self, page_num: int, pdf_rect: tuple,
                   fill: tuple = (1, 1, 1)) -> bool:
        """Bir dikdörtgen alanı sil / üzerini boya.

        Resimlerde sadece o alanın pikselleri silinir (resmin geri kalanı durur),
        alana denk gelen metin kaldırılır, üzeri `fill` rengiyle boyanır.
        """
        if not self.doc:
            return False
        page = self.doc[page_num]
        try:
            page.add_redact_annot(fitz.Rect(pdf_rect), fill=fill)
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_PIXELS,   # resmin sadece bu kısmını sil
                graphics=0,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            self.modified = True
            return True
        except Exception as e:
            print(f"[erase_area] HATA: {e}")
            return False

    def insert_image_file(self, page_num: int, pdf_rect: tuple, file_path: str) -> bool:
        if not self.doc:
            return False
        try:
            self.doc[page_num].insert_image(fitz.Rect(pdf_rect), filename=file_path)
            self.modified = True
            return True
        except Exception:
            return False

    # ── Kaydet / Kapat ────────────────────────────────────────────────────────

    def content_rect(self, page_num: int) -> tuple:
        """Sayfadaki metinlerin kapladığı alan (kenar boşlukları içi).
        Metin yoksa 36 pt (≈1.27 cm) kenar boşluklu sayfa alanı."""
        page = self.doc[page_num]
        r = fitz.Rect()
        for b in page.get_text("blocks"):
            if b[6] == 0:                         # sadece metin blokları
                r |= fitz.Rect(b[:4])
        if r.is_empty:
            r = page.rect + (36, 36, -36, -36)
        return (r.x0, r.y0, r.x1, r.y1)

    def text_block_rects(self, page_num: int) -> list:
        return [tuple(b[:4]) for b in self.doc[page_num].get_text("blocks") if b[6] == 0]

    def save(self, path: str | None = None) -> bool:
        """Her zaman tam kayıt: önce aynı klasöre geçici dosya, sonra yer değiştir.

        Eskiden saveIncr() kullanılıyordu; üretici datasheet'lerinin çoğu açılırken
        MuPDF tarafından "onarıldığı" için artımlı kayıt reddediliyor, yedek yol da
        "save to original must be incremental" hatasıyla düşüyordu → hiç kaydetmiyordu.
        Geçici dosya + os.replace ayrıca yarıda kesilen kayıtta orijinali korur.
        """
        if not self.doc:
            return False
        self.last_error = ""
        target = os.path.abspath(path or self.path)
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix="~pdfim_",
                                       dir=os.path.dirname(target))
            os.close(fd)
            self.doc.save(tmp, garbage=3, deflate=True)
            os.replace(tmp, target)
            tmp = None
        except PermissionError:
            self.last_error = ("Dosya başka bir programda açık (ör. Adobe, Edge, Outlook önizleme) "
                               "ya da klasöre yazma izniniz yok.\n"
                               "O programı kapatıp tekrar deneyin veya 'Farklı Kaydet' kullanın.")
            return False
        except Exception as e:
            self.last_error = f"Kayıt sırasında hata oluştu.\n({e})"
            return False
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
        self.path = target
        self.modified = False
        return True

    def close(self):
        if self.doc:
            self.doc.close()
            self.doc = None
        for f in self._font_tmpfiles:
            try:
                os.remove(f)
            except Exception:
                pass
        self._font_tmpfiles.clear()
        self._font_cache.clear()
        self._font_objs.clear()

    # ── Font yönetimi ─────────────────────────────────────────────────────────

    def _get_font_kwargs(self, page: fitz.Page, span_info: dict) -> dict:
        """
        Öncelik sırası:
          1. PDF'deki gömülü orijinal font (bold/italic dahil tam kopya)
          2. Eşleşen Windows sistem fontu (bold/italic dikkate alınır)
          3. Helvetica (ASCII) veya Arial (Türkçe/unicode)
        """
        span_font = span_info.get("font", "")
        flags     = span_info.get("flags", 0)
        is_bold   = bool(flags & 16)
        is_italic = bool(flags & 2)

        # Cache kontrolü
        cache_key = span_font
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        # 1. Orijinal gömülü fontu çıkarmayı dene
        result = self._extract_embedded_font(page, span_font)

        # 2. Sistem fontuna bak
        if not result:
            result = self._find_system_font(span_font, is_bold, is_italic)

        # 3. Son çare fallback
        if not result:
            text = span_info.get("text", "")
            if any(ord(c) > 127 for c in text):
                f = os.path.join(_FONTS_DIR, _ARIAL_VARIANTS[(is_bold, is_italic)])
                if os.path.exists(f):
                    result = {"fontfile": f, "fontname": f"PDFimArial{int(is_bold)}{int(is_italic)}"}
            if not result:
                result = {"fontname": "helv"}

        self._font_cache[cache_key] = result
        return result

    def _extract_embedded_font(self, page: fitz.Page, span_font: str) -> dict | None:
        """PDF'deki gömülü fontu geçici dosyaya çıkar"""
        span_lower = span_font.lower().replace(" ", "").replace("-", "").replace("_", "")

        for f in page.get_fonts(full=True):
            xref      = f[0]
            basefont  = f[3]  # "Arial-BoldMT" gibi
            fontname  = f[4]  # PDF içindeki referans adı

            base_lower = basefont.lower().replace(" ", "").replace("-", "").replace("_", "")
            name_lower = fontname.lower().replace(" ", "").replace("-", "").replace("_", "")

            # İsim eşleşmesi — tam veya kısmi
            match = (
                span_lower == base_lower or
                span_lower == name_lower or
                span_lower in base_lower or
                base_lower in span_lower or
                span_lower[:6] == base_lower[:6]   # ilk 6 karakter yeterli
            )
            if not match:
                continue

            try:
                font_data = self.doc.extract_font(xref)
                content   = font_data.get("content", b"")
                ext       = font_data.get("ext", "ttf") or "ttf"
                if not content or len(content) < 200:
                    continue

                tmp = tempfile.NamedTemporaryFile(
                    suffix=f".{ext}", delete=False, prefix="pdfim_font_"
                )
                tmp.write(content)
                tmp.close()
                self._font_tmpfiles.append(tmp.name)

                return {"fontfile": tmp.name, "fontname": f"EF{xref}"}
            except Exception:
                continue

        return None

    def _find_system_font(self, span_font: str, bold: bool, italic: bool) -> dict | None:
        """Span font adından Windows sistem fontunu bul"""
        fn = span_font.lower()
        # Stil kelimelerini temizle
        for s in ["bolditalic", "boldoblique", "bold", "italic", "oblique",
                  "regular", "roman", "medium", "light", "black", "mt", "ps"]:
            fn = fn.replace(s, "")
        fn = fn.replace("-", "").replace(" ", "").replace("_", "").strip()

        # Aile → (normal, bold, italic, bolditalic) dosya adları
        FAMILIES = {
            "arial":     ("arial",    "arialbd",  "ariali",   "arialbi"),
            "helvetica": ("arial",    "arialbd",  "ariali",   "arialbi"),
            "calibri":   ("calibri",  "calibrib", "calibrii", "calibriz"),
            "times":     ("times",    "timesbd",  "timesi",   "timesbi"),
            "courier":   ("cour",     "courbd",   "couri",    "courbi"),
            "georgia":   ("georgia",  "georgiab", "georgiai", "georgiaz"),
            "verdana":   ("verdana",  "verdanab", "verdanai", "verdanaz"),
            "tahoma":    ("tahoma",   "tahomabd", "tahoma",   "tahomabd"),
            "segoeui":   ("segoeui",  "segoeuib", "segoeuii", "segoeuiz"),
        }
        idx = (1 if (bold and not italic) else
               2 if (not bold and italic) else
               3 if (bold and italic) else 0)

        for key, variants in FAMILIES.items():
            if key in fn or fn in key or fn[:5] == key[:5]:
                path = os.path.join(_FONTS_DIR, variants[idx] + ".ttf")
                if not os.path.exists(path):
                    path = os.path.join(_FONTS_DIR, variants[0] + ".ttf")
                if os.path.exists(path):
                    fname = os.path.basename(path).replace(".ttf", "")
                    return {"fontfile": path, "fontname": f"SYS_{fname}"}

        return None

    def _int_to_rgb(self, color_int: int) -> tuple:
        return (
            ((color_int >> 16) & 0xFF) / 255,
            ((color_int >> 8)  & 0xFF) / 255,
            (color_int & 0xFF)         / 255,
        )
