"""PDFim web sunucusu — masaüstüyle aynı arayüz (ui/) ve PDF motoru (editor.py), tarayıcıdan.

    uvicorn server:app --host 0.0.0.0 --port 8000

Her tarayıcı oturumunun kendi belgesi ve geri alma yığını vardır (çerez). Belgeler yalnız bellekte
ve oturum klasöründe durur; hareketsiz oturum silinir. Herkese açık çalıştığı için:
  - API yalnız WEB_METHODS'taki metotları açar (open_path gibi sunucuda dosya okuyanlar kapalı),
  - yükleme boyutu, sayfa sayısı, oturum sayısı ve istek hızı sınırlıdır,
  - PyMuPDF AGPL lisanslıdır: kaynak kod bağlantısı (PDFIM_SOURCE_URL) arayüzde gösterilir.
"""

import logging
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
from collections import OrderedDict, defaultdict
from urllib.parse import quote

import fitz
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from bridge import Api, DocState
from page_server import PageCache

log = logging.getLogger("pdfim")

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
DATA_DIR = os.environ.get("PDFIM_DATA_DIR") or os.path.join(tempfile.gettempdir(), "pdfim-web")
SOURCE_URL = os.environ.get("PDFIM_SOURCE_URL", "https://github.com/bakiucartasarim/pdfim")
DESKTOP_URL = os.environ.get("PDFIM_DESKTOP_URL", "https://github.com/bakiucartasarim/pdfim/releases/latest")
MAX_UPLOAD = int(os.environ.get("PDFIM_MAX_UPLOAD_MB", "50")) * 1024 * 1024
MAX_PAGES = int(os.environ.get("PDFIM_MAX_PAGES", "500"))
MAX_SESSIONS = int(os.environ.get("PDFIM_MAX_SESSIONS", "100"))
IDLE_SECONDS = int(os.environ.get("PDFIM_IDLE_MINUTES", "60")) * 60
WEB_UNDO = 10                       # masaüstünde 20; sunucuda bellek oturum sayısıyla çarpılır
SESSION_CACHE = 24 * 1024 * 1024    # oturum başına sayfa PNG önbelleği
RATE_PER_SEC, RATE_BURST = 40, 120  # IP başına; kaydırırken sayfa görüntüleri art arda istenir
COOKIE = "pdfim_sid"

# Tarayıcıdan çağrılabilen köprü metotları. Dosya pencereleri, Windows panosu ve sunucuda
# yol alan open_path bilerek yok.
WEB_METHODS = {
    "get_state", "page_layer", "system_fonts",
    "replace_text", "move_text", "insert_text",
    "select_text", "copy_text", "clipboard_info", "paste_text", "paste_image",
    "add_image_data", "move_image", "delete_image", "align_image",
    "erase_area", "undo", "redo",
}

fitz.TOOLS.mupdf_display_errors(False)   # bozuk PDF uyarıları günlüğü doldurmasın


class Session:
    def __init__(self, sid: str):
        self.sid = sid
        self.state = DocState()
        self.api = Api(self.state, on_doc_changed=self._doc_changed, web=True, max_undo=WEB_UNDO)
        self.cache = PageCache(SESSION_CACHE)
        self.dir = os.path.join(DATA_DIR, sid)
        os.makedirs(self.dir, exist_ok=True)
        self.upload: str | None = None     # parola sorulan son yükleme
        self.last = time.monotonic()

    def _doc_changed(self):
        self.cache.clear()

    def close(self):
        with self.state.lock:
            self.state.editor.close()
        shutil.rmtree(self.dir, ignore_errors=True)


_sessions: "OrderedDict[str, Session]" = OrderedDict()
_sessions_lock = threading.Lock()


def _session(request: Request, create: bool = True) -> tuple[Session | None, bool]:
    """(oturum, yeni mi). Çerez yoksa ya da oturum silinmişse yenisi açılır."""
    sid = request.cookies.get(COOKIE, "")
    with _sessions_lock:
        s = _sessions.get(sid) if re.fullmatch(r"[\w-]{20,64}", sid or "") else None
        if s:
            s.last = time.monotonic()
            _sessions.move_to_end(sid)
            return s, False
        if not create:
            return None, False
        if len(_sessions) >= MAX_SESSIONS:
            # En uzun süredir hareketsiz oturum 5 dakikadan eskiyse yer açılır, değilse sunucu dolu
            oldest = next(iter(_sessions.values()))
            if time.monotonic() - oldest.last < 300:
                raise HTTPException(503, "Sunucu şu an dolu, lütfen biraz sonra tekrar deneyin.")
            _sessions.pop(oldest.sid).close()
        s = Session(secrets.token_urlsafe(24))
        _sessions[s.sid] = s
        return s, True


def _set_cookie(request: Request, response: Response, s: Session):
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(COOKIE, s.sid, httponly=True, samesite="strict", secure=https,
                        max_age=IDLE_SECONDS)


def _janitor():
    """Hareketsiz oturumları ve (yeniden başlatmadan kalan) sahipsiz klasörleri temizle."""
    while True:
        time.sleep(60)
        now = time.monotonic()
        with _sessions_lock:
            stale = [s for s in _sessions.values() if now - s.last > IDLE_SECONDS]
            for s in stale:
                _sessions.pop(s.sid, None)
            live = set(_sessions)
        for s in stale:
            s.close()
        for ip in [ip for ip, b in list(_buckets.items()) if now - b[1] > 600]:
            _buckets.pop(ip, None)
        try:
            for name in os.listdir(DATA_DIR):
                if name not in live:
                    shutil.rmtree(os.path.join(DATA_DIR, name), ignore_errors=True)
        except OSError:
            pass


# ── Uygulama ─────────────────────────────────────────────────────────────────

app = FastAPI(title="PDFim", docs_url=None, redoc_url=None, openapi_url=None)
shutil.rmtree(DATA_DIR, ignore_errors=True)       # önceki çalışmadan kalan belgeler
os.makedirs(DATA_DIR, exist_ok=True)
threading.Thread(target=_janitor, daemon=True).start()

_buckets: dict = defaultdict(lambda: [RATE_BURST, time.monotonic()])


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/ui/"):
        # IP başına jeton kovası. Coolify/Traefik gerçek IP'yi X-Forwarded-For'un *sonuna* ekler;
        # ilk değeri istemci kendisi yazabilir (sınırı atlatmak için), o yüzden sonuncusu
        ip = (request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
              or (request.client.host if request.client else "?"))
        b = _buckets[ip]
        now = time.monotonic()
        b[0] = min(RATE_BURST, b[0] + (now - b[1]) * RATE_PER_SEC)
        b[1] = now
        if b[0] < 1:
            return JSONResponse({"ok": False, "error": "Çok fazla istek. Biraz yavaşlayın."}, 429)
        b[0] -= 1
    response = await call_next(request)
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data: blob:; "
                                    "style-src 'self' 'unsafe-inline'; script-src 'self'; "
                                    "connect-src 'self'; font-src 'self'; frame-ancestors 'none'")
    return response


@app.get("/")
def root():
    return RedirectResponse("/ui/index.html")


@app.get("/api/config")
def config(request: Request):
    s, new = _session(request)
    r = JSONResponse({"web": True, "sourceUrl": SOURCE_URL, "desktopUrl": DESKTOP_URL,
                      "maxUploadMb": MAX_UPLOAD // (1024 * 1024), "maxPages": MAX_PAGES,
                      "idleMinutes": IDLE_SECONDS // 60})
    _set_cookie(request, r, s)
    return r


@app.post("/api/{name}")
async def call(name: str, request: Request):
    if name not in WEB_METHODS:
        raise HTTPException(404)
    s, new = _session(request)
    try:
        args = await request.json()
    except ValueError:
        raise HTTPException(400, "Geçersiz istek.")
    if not isinstance(args, list):
        raise HTTPException(400, "Geçersiz istek.")
    try:
        result = await run_in_threadpool(getattr(s.api, name), *args)
    except TypeError:
        raise HTTPException(400, "Geçersiz istek.")
    except Exception:
        log.exception("api %s", name)
        result = {"ok": False, "error": "İşlem sırasında bir hata oluştu."}
    r = JSONResponse(result)
    if new:
        _set_cookie(request, r, s)
    return r


def _safe_name(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/")).strip() or "belge.pdf"
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name)[:120]
    return name if name.lower().endswith(".pdf") else name + ".pdf"


def _open_upload(s: Session, password: str | None) -> dict:
    r = s.api.open_path(s.upload, password)
    if r.get("ok") and len(r["state"]["pages"]) > MAX_PAGES:
        with s.state.lock:
            s.state.editor.close()
        return {"ok": False, "error": f"Belge {MAX_PAGES} sayfadan uzun; web sürümünde açılamaz. "
                                      "Masaüstü sürümünü kullanabilirsiniz."}
    return r


@app.post("/upload")
async def upload(request: Request, name: str = "belge.pdf"):
    s, new = _session(request)
    if int(request.headers.get("content-length") or 0) > MAX_UPLOAD:
        raise HTTPException(413, f"Dosya {MAX_UPLOAD // (1024 * 1024)} MB'tan büyük.")
    data = bytearray()
    async for chunk in request.stream():         # content-length'e güvenmeden de sınırla
        data += chunk
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"Dosya {MAX_UPLOAD // (1024 * 1024)} MB'tan büyük.")
    path = os.path.join(s.dir, _safe_name(name))
    for old in os.listdir(s.dir):                 # oturumda tek belge
        try:
            os.remove(os.path.join(s.dir, old))
        except OSError:
            pass
    with open(path, "wb") as f:
        f.write(data)
    s.upload = path
    r = JSONResponse(await run_in_threadpool(_open_upload, s, None))
    if new:
        _set_cookie(request, r, s)
    return r


@app.post("/reopen")
async def reopen(request: Request):
    """Parolalı PDF: son yüklenen dosyayı parolayla yeniden aç (dosya tekrar gönderilmez)."""
    s, _ = _session(request)
    body = await request.json()
    if not s.upload or not isinstance(body, dict):
        raise HTTPException(400)
    return await run_in_threadpool(_open_upload, s, str(body.get("password", "")))


@app.get("/download")
async def download(request: Request):
    s, _ = _session(request, create=False)
    out = s and await run_in_threadpool(s.api._export)
    if not out:
        raise HTTPException(404, "Açık belge yok.")
    data, name = out
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=\"belge.pdf\"; filename*=UTF-8''{quote(name)}",
        "Cache-Control": "no-store"})


@app.get("/page/{num}.png")
async def page(num: int, request: Request, v: str = ""):
    s, _ = _session(request, create=False)
    if not s:
        raise HTTPException(410)
    try:
        scale = min(8.0, max(0.1, float(request.query_params.get("s", "1.5"))))
    except ValueError:
        raise HTTPException(400)
    key = (v, num, round(scale, 3))
    data = s.cache.get(key)
    if data is None:
        data = await run_in_threadpool(s.state.render, num, scale, v)
        if data is None:
            raise HTTPException(410)
        s.cache.put(key, data)
    return Response(data, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=31536000, immutable"})


app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")
