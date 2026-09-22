"""Windows'a kurulu fontlar — aile adı → (kalın, italik) varyant dosyaları"""

import os
import re
import subprocess
import sys

try:
    import winreg
except ImportError:          # Windows dışı: font listesi boş kalır, fallback'ler çalışır
    winreg = None

_FONTS_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_REG_PATH = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"

# Uzundan kısaya: "Bold Italic" önce denenmeli, yoksa "Italic" olarak yakalanır
_STYLE_SUFFIXES = [
    ("bold italic",  (True,  True)),
    ("bold oblique", (True,  True)),
    ("bold",         (True,  False)),
    ("italic",       (False, True)),
    ("oblique",      (False, True)),
    ("regular",      (False, False)),
]

_cache: dict | None = None


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def system_fonts() -> dict:
    """{"Arial": {(False, False): "C:/.../arial.ttf", (True, False): ".../arialbd.ttf", ...}}"""
    global _cache
    if _cache is not None:
        return _cache
    fams: dict = {}
    if winreg is None:                       # Linux (web sunucusu): fontconfig
        _cache = _scan_fontconfig()
        return _cache
    # HKCU: kullanıcının yönetici yetkisi olmadan kurduğu fontlar
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(root, _REG_PATH)
        except OSError:
            continue
        with key:
            i = 0
            while True:
                try:
                    name, file, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1
                if not isinstance(file, str) or not file.lower().endswith((".ttf", ".otf", ".ttc")):
                    continue
                path = file if os.path.isabs(file) else os.path.join(_FONTS_DIR, file)
                if not os.path.exists(path):
                    continue
                # "Cambria & Cambria Math (TrueType)" → "Cambria" (.ttc'nin ilk fontu)
                name = re.sub(r"\s*\((TrueType|OpenType)\)\s*$", "", name).split("&")[0].strip()
                style = (False, False)
                for suffix, st in _STYLE_SUFFIXES:
                    if name.lower().endswith(" " + suffix):
                        name, style = name[: -len(suffix) - 1].strip(), st
                        break
                if name:
                    fams.setdefault(name, {}).setdefault(style, path)
    _cache = fams
    return fams


def _scan_fontconfig() -> dict:
    """fc-list çıktısından aile → (kalın, italik) → dosya. Light/Medium gibi ara
    ağırlıklar atlanır; biçim çubuğunda yalnız normal/kalın/italik seçiliyor."""
    try:
        out = subprocess.run(["fc-list", "--format", "%{family[0]}\\t%{style[0]}\\t%{file}\\n"],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    fams: dict = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[2].lower().endswith((".ttf", ".otf", ".ttc")):
            continue
        family, style, path = parts[0].strip(), parts[1].lower(), parts[2]
        bold = "bold" in style
        italic = "italic" in style or "oblique" in style
        rest = re.sub(r"bold|italic|oblique", "", style).strip()
        if family and rest in ("", "regular", "book", "roman", "normal"):
            fams.setdefault(family, {}).setdefault((bold, italic), path)
    return fams


# Metin yazılırken son çare: belgedeki font da eşleşen sistem fontu da karakteri
# içermiyorsa. Liberation Sans, Arial ile aynı genişliklerde (Linux'taki karşılığı).
_FALLBACK_FAMILIES = ("Arial", "Liberation Sans", "DejaVu Sans", "Noto Sans")


def fallback_file(bold: bool, italic: bool) -> str | None:
    for family in _FALLBACK_FAMILIES:
        path = font_file(family, bold, italic)
        if path:
            return path
    if sys.platform == "win32":              # kayıt defteri okunamadıysa bile Arial oradadır
        name = {(False, False): "arial", (True, False): "arialbd",
                (False, True): "ariali", (True, True): "arialbi"}[(bold, italic)]
        path = os.path.join(_FONTS_DIR, name + ".ttf")
        return path if os.path.exists(path) else None
    return None


def font_file(family: str, bold: bool, italic: bool) -> str | None:
    """İstenen varyant yoksa sırayla: sadece kalın/italik, normal, ailenin herhangi bir dosyası"""
    variants = system_fonts().get(family)
    if not variants:
        return None
    for key in ((bold, italic), (bold, False), (False, italic), (False, False)):
        if key in variants:
            return variants[key]
    return next(iter(variants.values()))


def match_family(pdf_font_name: str) -> str | None:
    """PDF'teki font adını ("ABCDEF+Arial-BoldMT") kurulu bir aileyle eşleştir"""
    if not pdf_font_name:
        return None
    name = pdf_font_name.split("+")[-1]                     # subset öneki
    by_norm = {_norm(f): f for f in system_fonts()}
    # Önce tam ad: "Segoe UI Semibold" kendi başına bir aile; "bold"u silersek "Semi" kalır
    if _norm(name) in by_norm:
        return by_norm[_norm(name)]
    name = re.sub(r"(?i)[-,_ ]?(bold|italic|oblique|regular|roman|mt|ps)+$", "", name)
    name = re.sub(r"(?i)(bold|italic|oblique|regular|roman|mt|ps)+$", "", name)
    key = _norm(name)
    if not key:
        return None
    if key in by_norm:
        return by_norm[key]
    # "TimesNewRomanPSMT" → "timesnewroman", "Helvetica" → Arial muadili
    aliases = {"helvetica": "Arial", "helv": "Arial", "times": "Times New Roman",
               "timesroman": "Times New Roman", "courier": "Courier New"}
    if key in aliases and aliases[key] in system_fonts():
        return aliases[key]
    # En uzun ortak önek — "arialnarrow" > "arial"
    best = max(by_norm, key=lambda n: (key.startswith(n) or n.startswith(key)) * len(n), default=None)
    if best and (key.startswith(best) or best.startswith(key)) and len(best) >= 4:
        return by_norm[best]
    return None
