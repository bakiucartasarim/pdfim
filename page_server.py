"""Yerel HTTP sunucusu — arayüz dosyalarını ve PyMuPDF ile çizilmiş sayfa görüntülerini sunar.

Sayfa görüntüleri base64 olarak JS köprüsünden geçirilmek yerine buradan <img> ile yüklenir:
tarayıcı kendi önbelleğini ve paralel indirmesini kullanır, köprü tıkanmaz.

Yalnız 127.0.0.1'e bağlanır; adres rastgele bir belirteçle başlar, böylece makinedeki başka bir
program portu tahmin etse bile belgeyi okuyamaz.
"""

import mimetypes
import os
import re
import secrets
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")

_PAGE_RE = re.compile(r"^page/(\d+)\.png$")

# Çok büyük ölçek hem belleği hem çizim süresini patlatır (A4 @ 8x ≈ 4700x6700 px)
_MIN_SCALE, _MAX_SCALE = 0.1, 8.0
_CACHE_LIMIT = 200 * 1024 * 1024   # PNG baytı


class PageCache:
    """(revizyon, sayfa, ölçek) → PNG baytları. Belge her değiştiğinde revizyon artar,
    eski girdiler bir daha istenmez ve zamanla dışarı itilir."""

    def __init__(self):
        self._items: OrderedDict[tuple, bytes] = OrderedDict()
        self._bytes = 0
        # Sunucu her isteği ayrı iş parçacığında karşılar; clear() ise köprüden gelir
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            data = self._items.get(key)
            if data is not None:
                self._items.move_to_end(key)   # en son kullanılan sona
            return data

    def put(self, key, data: bytes):
        with self._lock:
            if key in self._items:
                return
            self._items[key] = data
            self._bytes += len(data)
            self._trim()

    def clear(self):
        with self._lock:
            self._items.clear()
            self._bytes = 0

    def _trim(self):
        """En uzun süredir kullanılmayanları at (self._items en eskiden en yeniye sıralı;
        kilit içinde çağrılır). Tarayıcı da kendi önbelleğini tuttuğu için bu yalnız
        "geri dönülen sayfa yeniden çizilmesin" diye var; küçük bir sınır yeter."""
        while self._bytes > _CACHE_LIMIT and len(self._items) > 1:
            _, old = self._items.popitem(last=False)
            self._bytes -= len(old)


class PageServer:
    def __init__(self, ui_dir: str, state):
        """state: bridge.DocState — editor, lock ve rev alanlarını taşır."""
        self.ui_dir = os.path.abspath(ui_dir)
        self.state = state
        self.token = secrets.token_urlsafe(16)
        self.cache = PageCache()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/{self.token}/"

    def start(self):
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def stop(self):
        self._httpd.shutdown()

    # ── İstek işleme ─────────────────────────────────────────────────────────

    def _render(self, page_num: int, scale: float, version: str) -> bytes | None:
        key = (version, page_num, round(scale, 3))
        data = self.cache.get(key)
        if data is not None:
            return data
        # MuPDF aynı belgeye iki iş parçacığından aynı anda dokunulmasına dayanıklı değil;
        # köprüdeki düzenleme işlemleri de aynı kilidi tutar.
        with self.state.lock:
            ed = self.state.editor
            if not ed.doc or not 0 <= page_num < ed.page_count() \
                    or version != self.state.version(page_num):
                return None
            data = ed.render_page(page_num, scale)
        self.cache.put(key, data)
        return data

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):   # konsolu her istekte doldurmasın
                pass

            def do_GET(self):
                url = urlparse(self.path)
                prefix = f"/{server.token}/"
                if not url.path.startswith(prefix):
                    return self.send_error(404)
                rel = url.path[len(prefix):]

                m = _PAGE_RE.match(rel)
                if m:
                    q = parse_qs(url.query)
                    try:
                        scale = min(_MAX_SCALE, max(_MIN_SCALE, float(q.get("s", ["1.5"])[0])))
                    except ValueError:
                        return self.send_error(400)
                    data = server._render(int(m.group(1)), scale, q.get("v", [""])[0])
                    if data is None:
                        return self.send_error(410)   # eski sürüm ya da belge kapandı
                    # URL sayfa sürümünü içerdiği için içerik hiç değişmez → uzun süre önbelleklenebilir
                    return self._send(data, "image/png", "max-age=31536000, immutable")

                if rel.startswith("ui/"):
                    return self._send_file(rel[3:])
                self.send_error(404)

            def _send_file(self, rel: str):
                path = os.path.abspath(os.path.join(server.ui_dir, rel))
                # ../ ile ui klasörünün dışına çıkılmasın
                if not path.startswith(server.ui_dir + os.sep) or not os.path.isfile(path):
                    return self.send_error(404)
                with open(path, "rb") as f:
                    data = f.read()
                ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
                self._send(data, ctype, "no-cache")

            def _send(self, data: bytes, ctype: str, cache: str):
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", cache)
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass   # kullanıcı hızla kaydırdı, tarayıcı isteği iptal etti

        return Handler
