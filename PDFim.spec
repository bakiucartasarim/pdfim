# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('pdfim.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt6.QtNetwork', 'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets',
        'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets',
        'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtBluetooth', 'PyQt6.QtDBus', 'PyQt6.QtDesigner',
        'PyQt6.QtHelp', 'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets',
        'PyQt6.QtNfc', 'PyQt6.QtPositioning', 'PyQt6.QtQml',
        'PyQt6.QtQuick', 'PyQt6.QtQuickWidgets', 'PyQt6.QtRemoteObjects',
        'PyQt6.QtSensors', 'PyQt6.QtSerialPort', 'PyQt6.QtSql',
        'PyQt6.QtSvg', 'PyQt6.QtSvgWidgets', 'PyQt6.QtTest',
        'PyQt6.QtTextToSpeech', 'PyQt6.QtXml', 'PyQt6.QtWebChannel',
        'tkinter', 'unittest', 'pdb', 'doctest', 'pydoc', 'curses',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

REMOVE = {
    'opengl32sw.dll', 'qt6pdf.dll', 'qt6network.dll',
    'qt6sql.dll', 'qt6xml.dll', 'qt6opengl.dll',
    'qt6qml.dll', 'qt6quick.dll', 'qt6svg.dll',
    'qt6multimedia.dll', 'd3dcompiler_47.dll',
    '_avif.cp312-win_amd64.pyd', '_heif.cp312-win_amd64.pyd',
}
a.binaries = TOC([
    (d, s, k) for (d, s, k) in a.binaries
    if os.path.basename(d).lower() not in REMOVE
])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='PDFim',
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
    icon='pdfim.ico',
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name='PDFim',
)
