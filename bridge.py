"""JS ↔ Python köprüsü — pywebview js_api olarak arayüze açılır.

JS tarafında her public metot `window.pywebview.api.<ad>(...)` ile çağrılır ve Promise döner.
pywebview public nitelikleri de dışarı açtığı için iç durum `_` ile başlayan adlarda tutulur.
"""

import json
import os
import threading

import webview

from editor import PDFEditor

MAX_UNDO = 20
MAX_RECENT = 10
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PDFim")
_RECENT_PATH = os.path.join(APPDATA_DIR, "recent.json")
_PDF_TYPES = ("PDF dosyaları (*.pdf)",)


class DocState:
    """Köprü ile sayfa sunucusunun paylaştığı durum.

    rev: belge her değiştiğinde artar. Sayfa URL'lerine eklenir, böylece tarayıcı
    eski görüntüyü önbellekten göstermez.
    """

    def __init__(self):
        self.editor = PDFEditor()
        self.lock = threading.RLock()
        self.rev = 0


class Api:
    def __init__(self, state: DocState, on_doc_changed=None):
        self._state = state
        self._window: webview.Window | None = None
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []
        self._recent: list[str] = _load_recent()
        self._on_doc_changed = on_doc_changed   # sayfa önbelleğini temizlemek için

    def _attach(self, window: webview.Window):
        self._window = window

    # ── Durum ────────────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        with self._state.lock:
            ed = self._state.editor
            if not ed.doc:
                return {"open": False, "recent": self._recent}
            return {
                "open": True,
                "path": ed.path,
                "name": os.path.basename(ed.path) or "Adsız.pdf",
                "rev": self._state.rev,
                "modified": ed.modified,
                "canUndo": bool(self._undo),
                "canRedo": bool(self._redo),
                # PDF noktası (1/72 inç) cinsinden sayfa boyutları; JS yerleşimi bunlarla hesaplar
                "pages": [[p.rect.width, p.rect.height] for p in ed.doc],
                "recent": self._recent,
            }

    def _changed(self):
        """Belge içeriği değişti: revizyonu artır, başlığı güncelle."""
        self._state.rev += 1
        if self._on_doc_changed:
            self._on_doc_changed()
        self._update_title()

    def _update_title(self):
        if not self._window:
            return
        ed = self._state.editor
        if ed.doc:
            star = "• " if ed.modified else ""
            self._window.set_title(f"{star}{os.path.basename(ed.path) or 'Adsız'} — PDFim")
        else:
            self._window.set_title("PDFim")

    # ── Dosya ────────────────────────────────────────────────────────────────

    def open_dialog(self) -> dict | None:
        """Dosya seçtirip açar. Kullanıcı vazgeçerse None."""
        if not self._confirm_discard():
            return None
        start = os.path.dirname(self._state.editor.path) if self._state.editor.path else ""
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
            self._state.editor.close()
            self._state.editor = ed = new
            self._undo.clear()
            self._redo.clear()
            self._changed()
        self._add_recent(ed.path)
        return {"ok": True, "state": self.get_state()}

    def save(self) -> dict:
        ed = self._state.editor
        if not ed.doc:
            return {"ok": False, "error": "Açık belge yok."}
        if not ed.path:
            return self.save_as()
        with self._state.lock:
            ok = ed.save()
        self._update_title()
        return {"ok": ok, "error": ed.last_error, "state": self.get_state()}

    def save_as(self) -> dict | None:
        ed = self._state.editor
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

    def _add_recent(self, path: str):
        self._recent = ([path] + [p for p in self._recent if p != path])[:MAX_RECENT]
        try:
            os.makedirs(APPDATA_DIR, exist_ok=True)
            with open(_RECENT_PATH, "w", encoding="utf-8") as f:
                json.dump(self._recent, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ── Geri al / yinele ─────────────────────────────────────────────────────
    # Her düzenleme öncesi belgenin tamamının bayt kopyası alınır (v1 ile aynı yöntem).
    # Basit ve her işlem türü için doğru; bedeli 20 × dosya boyutu kadar bellek.

    def _snapshot(self):
        """Değiştiren her köprü metodu, değişiklikten önce bunu çağırır (kilit içinde)."""
        self._undo.append(self._state.editor.doc.tobytes())
        del self._undo[:-MAX_UNDO]
        self._redo.clear()

    def _restore(self, src: list, dst: list) -> dict:
        with self._state.lock:
            ed = self._state.editor
            if not src or not ed.doc:
                return self.get_state()
            dst.append(ed.doc.tobytes())
            path = ed.path
            ed.open_from_bytes(src.pop(), path)
            self._changed()
            return self.get_state()

    def undo(self) -> dict:
        return self._restore(self._undo, self._redo)

    def redo(self) -> dict:
        return self._restore(self._redo, self._undo)

    # ── Pencere ──────────────────────────────────────────────────────────────

    def _confirm_discard(self) -> bool:
        """Kaydedilmemiş değişiklik varsa sorar. True → belge bırakılabilir (kapat / başkasını aç)."""
        ed = self._state.editor
        if not ed.doc or not ed.modified:
            return True
        return self._window.create_confirmation_dialog(
            "Kaydedilmemiş değişiklikler",
            f"{os.path.basename(ed.path) or 'Belge'} dosyasındaki değişiklikler kaydedilmedi.\n"
            "Kaydetmeden devam edilsin mi?")


def _load_recent() -> list:
    try:
        with open(_RECENT_PATH, encoding="utf-8") as f:
            return [p for p in json.load(f) if os.path.exists(p)][:MAX_RECENT]
    except (OSError, ValueError):
        return []
