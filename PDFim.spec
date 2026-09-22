# -*- mode: python ; coding: utf-8 -*-
"""PDFim v2 paketleme — venv_build\\Scripts\\python -m PyInstaller PDFim.spec --noconfirm --clean

Arayüz HTML (ui/), pencere pywebview + Windows'un WebView2'si. WebView2 çalışma zamanı
Windows 10/11'de kurulu gelir; pywebview'ın .NET köprüsü (pythonnet) pakete girer.
"""
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [("ui", "ui"), ("pdfim.ico", ".")]
binaries = []
hiddenimports = ["webview.platforms.edgechromium", "clr"]

# pywebview'ın WebView2 DLL'leri ve pythonnet'in çalışma zamanı
for pkg in ("webview", "pythonnet", "clr_loader"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files("proxy_tools")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # v2'de PyQt6 yok; tkinter ve pywebview'ın diğer platform kabukları da gereksiz
        "PyQt6", "PySide6", "PyQt5", "tkinter", "gi", "qtpy",
        "webview.platforms.cocoa", "webview.platforms.gtk", "webview.platforms.qt",
        "webview.platforms.android", "webview.platforms.cef",
        # http.server / email: pywebview'in yerel sunucusu (wsgiref) kullanıyor, dışlanamaz
        "unittest", "pdb", "doctest", "pydoc", "curses",
        "pytest", "setuptools", "pip",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

# Not: webview/lib/runtimes altındaki win-arm64 / win-x86 klasörleri silinemez —
# pywebview (edgechromium.py) açılışta üçünün de yolunu Path'e ekliyor, yoksa çöküyor.

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PDFim",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="pdfim.ico",
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name="PDFim",
)
