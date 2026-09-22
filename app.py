"""PDFim v2 giriş noktası — WebView2 (pywebview) penceresi + HTML arayüz.

Arayüz ui/ klasöründe; PDF işlemleri editor.py (PyMuPDF) üzerinden bridge.Api ile yapılır.
"""

import datetime
import json
import os
import sys
import traceback

import webview
from webview.dom import DOMEventHandler

from bridge import Api, DocState, APPDATA_DIR
from page_server import PageServer


def _resource(name: str) -> str:
    """PyInstaller paketinde (_MEIPASS) ya da kaynak klasörde bir dosyanın yolu"""
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), name)


def _write_crash_log(exc_type, exc_value, exc_tb):
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        with open(os.path.join(APPDATA_DIR, "crash.log"), "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.datetime.now().isoformat()} ===\n")
            f.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    except Exception:
        pass


def main():
    sys.excepthook = lambda *exc: (_write_crash_log(*exc), sys.__excepthook__(*exc))
    if sys.platform == "win32":
        # Kendi AppUserModelID'si olmazsa görev çubuğunda Python'un ikonu görünür
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PDFim.Editor")
        except Exception:
            pass

    state = DocState()
    server = PageServer(_resource("ui"), state)
    api = Api(state, on_doc_changed=server.cache.clear)
    server.start()

    window = webview.create_window(
        "PDFim", server.base_url + "ui/index.html", js_api=api,
        width=1400, height=900, min_size=(1000, 640), background_color="#F1F5F9",
        text_select=True)
    api._attach(window)

    # Kaydedilmemiş değişiklik varken kapatma: False dönmek kapanmayı iptal eder
    window.events.closing += lambda: api._confirm_discard()

    def push(result):
        """Python tarafında açılan belgeyi (sürükle-bırak, komut satırı) arayüze bildir."""
        window.evaluate_js(f"window.app && app.onExternalOpen({json.dumps(result)})")

    def on_drop(e):
        files = e.get("dataTransfer", {}).get("files", [])
        pdfs = [f.get("pywebviewFullPath") for f in files
                if f.get("pywebviewFullPath", "").lower().endswith(".pdf")]
        if pdfs and api._confirm_discard():
            push(api.open_path(pdfs[0]))

    argv_pdf = [a for a in sys.argv[1:2] if a.lower().endswith(".pdf")]

    def on_loaded():
        # DOM dinleyicileri sayfayla birlikte yok olur; yeniden yüklemede (F5) tekrar bağlanmalı.
        # Tarayıcı varsayılanı bırakılan PDF'i kendi görüntüleyicisinde açmak; bunu engelle
        window.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, True)
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        # Dosya ilişkilendirme (PDFim.exe dosya.pdf) — yalnız ilk yüklemede
        if argv_pdf:
            push(api.open_path(argv_pdf.pop()))

    window.events.loaded += on_loaded

    webview.start(gui="edgechromium", debug="--debug" in sys.argv,
                  icon=_resource("pdfim.ico"))


if __name__ == "__main__":
    main()
