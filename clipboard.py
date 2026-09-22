"""Windows panosu — metin okuma/yazma ve resim okuma (ctypes, ek bağımlılık yok).

v1'de bu işi Qt yapıyordu. WebView2 içinden navigator.clipboard ile resim okumak izin
istemine takılabildiği için pano Python tarafında tutulur.
"""

import ctypes
import time
from ctypes import wintypes as w

import fitz

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.OpenClipboard.argtypes = [w.HWND]
_user32.OpenClipboard.restype = w.BOOL
_user32.CloseClipboard.restype = w.BOOL
_user32.EmptyClipboard.restype = w.BOOL
_user32.IsClipboardFormatAvailable.argtypes = [w.UINT]
_user32.IsClipboardFormatAvailable.restype = w.BOOL
_user32.GetClipboardData.argtypes = [w.UINT]
_user32.GetClipboardData.restype = w.HANDLE
_user32.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
_user32.SetClipboardData.restype = w.HANDLE
_user32.RegisterClipboardFormatW.argtypes = [w.LPCWSTR]
_user32.RegisterClipboardFormatW.restype = w.UINT
_kernel32.GlobalLock.argtypes = [w.HGLOBAL]
_kernel32.GlobalLock.restype = w.LPVOID
_kernel32.GlobalUnlock.argtypes = [w.HGLOBAL]
_kernel32.GlobalSize.argtypes = [w.HGLOBAL]
_kernel32.GlobalSize.restype = ctypes.c_size_t
_kernel32.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = w.HGLOBAL
_kernel32.GlobalFree.argtypes = [w.HGLOBAL]

CF_DIB = 8
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
_CF_PNG = _user32.RegisterClipboardFormatW("PNG")   # Ekran Alıntısı Aracı, tarayıcılar, Office


class _Open:
    """Pano başka bir programda kısa süre açık olabilir (ör. kopyalayan program) → birkaç kez dene."""

    def __enter__(self):
        for _ in range(20):
            if _user32.OpenClipboard(None):
                return self
            time.sleep(0.01)
        raise OSError("Pano başka bir program tarafından kullanılıyor.")

    def __exit__(self, *exc):
        _user32.CloseClipboard()


def _read(fmt: int) -> bytes | None:
    h = _user32.GetClipboardData(fmt)
    if not h:
        return None
    p = _kernel32.GlobalLock(h)
    if not p:
        return None
    try:
        return ctypes.string_at(p, _kernel32.GlobalSize(h))
    finally:
        _kernel32.GlobalUnlock(h)


def get_text() -> str:
    try:
        with _Open():
            if not _user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return ""
            data = _read(CF_UNICODETEXT)
    except OSError:
        return ""
    if not data:
        return ""
    return data.decode("utf-16-le", errors="replace").split("\0", 1)[0]


def set_text(text: str) -> bool:
    data = text.encode("utf-16-le") + b"\0\0"
    h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not h:
        return False
    p = _kernel32.GlobalLock(h)
    if not p:
        _kernel32.GlobalFree(h)
        return False
    ctypes.memmove(p, data, len(data))
    _kernel32.GlobalUnlock(h)
    try:
        with _Open():
            _user32.EmptyClipboard()
            if _user32.SetClipboardData(CF_UNICODETEXT, h):
                return True          # bellek artık panonun
    except OSError:
        pass
    _kernel32.GlobalFree(h)
    return False


def has_image() -> bool:
    try:
        with _Open():
            return bool(_user32.IsClipboardFormatAvailable(_CF_PNG) or
                        _user32.IsClipboardFormatAvailable(CF_DIB))
    except OSError:
        return False


def get_image_png() -> bytes | None:
    """Panodaki resim PNG olarak. Önce "PNG" biçimi (şeffaflık korunur), yoksa CF_DIB."""
    try:
        with _Open():
            if _user32.IsClipboardFormatAvailable(_CF_PNG):
                data = _read(_CF_PNG)
                if data:
                    return data
            if not _user32.IsClipboardFormatAvailable(CF_DIB):
                return None
            dib = _read(CF_DIB)
    except OSError:
        return None
    if not dib or len(dib) < 40:
        return None
    try:
        return fitz.Pixmap(_dib_to_bmp(dib)).tobytes("png")
    except Exception:
        return None


def _dib_to_bmp(dib: bytes) -> bytes:
    """CF_DIB (başlıksız bitmap) → .bmp dosyası: önüne 14 baytlık BITMAPFILEHEADER eklenir"""
    header_size = int.from_bytes(dib[0:4], "little")
    bit_count = int.from_bytes(dib[14:16], "little")
    compression = int.from_bytes(dib[16:20], "little")
    colors_used = int.from_bytes(dib[32:36], "little")
    table = 0
    if bit_count <= 8:
        table = (colors_used or (1 << bit_count)) * 4
    elif compression == 3 and header_size == 40:   # BI_BITFIELDS: 3 renk maskesi başlıktan sonra
        table = 12
    offset = 14 + header_size + table
    file_header = b"BM" + (14 + len(dib)).to_bytes(4, "little") + b"\0\0\0\0" + offset.to_bytes(4, "little")
    return file_header + dib
