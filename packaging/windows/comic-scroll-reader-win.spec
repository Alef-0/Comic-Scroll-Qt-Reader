# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for Comic Scroll Reader on Windows."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT_DIR = Path.cwd()

datas = [
    (str(ROOT_DIR / 'comic_scroll_reader' / 'assets' / 'csr_app_icon.png'), 'comic_scroll_reader/assets'),
    (str(ROOT_DIR / 'comic_scroll_reader' / 'assets' / 'csr_app_icon.ico'), 'comic_scroll_reader/assets'),
]
binaries = []
hiddenimports = [
    'comic_scroll_reader',
    'comic_scroll_reader.main_window',
    'comic_scroll_reader.scroll_reader',
    'comic_scroll_reader.single_viewer',
    'comic_scroll_reader.hud_overlay',
    'comic_scroll_reader.shortcuts_dialog',
    'comic_scroll_reader.about_dialog',
    'comic_scroll_reader.welcome_widget',
    'comic_scroll_reader.image_pipeline',
    'comic_scroll_reader.pdf_handler',
    'comic_scroll_reader.input_controls',
    'comic_scroll_reader.resources',
]

# Ensure pypdfium2 binary libraries (pdfium.dll) and data are bundled
for pkg in ('pypdfium2', 'pypdfium2_raw'):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# In excludes, explicitly prune heavy unused PyQt6 modules
qt_excludes = [
    'tkinter', 'matplotlib', 'scipy', 'numpy', 'pytest', 'unittest',
    'PyQt6.QtBluetooth', 'PyQt6.QtDesigner', 'PyQt6.QtHelp',
    'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets', 'PyQt6.QtNetwork',
    'PyQt6.QtNfc', 'PyQt6.QtPdf', 'PyQt6.QtPositioning', 'PyQt6.QtQml',
    'PyQt6.QtQuick', 'PyQt6.QtQuick3D', 'PyQt6.QtQuickWidgets',
    'PyQt6.QtRemoteObjects', 'PyQt6.QtSensors', 'PyQt6.QtSerialPort',
    'PyQt6.QtSpatialAudio', 'PyQt6.QtSql', 'PyQt6.QtSvg', 'PyQt6.QtTest',
    'PyQt6.QtVirtualKeyboard', 'PyQt6.QtWebChannel', 'PyQt6.QtWebSockets',
    'PyQt6.QtXml',
]

a = Analysis(
    [str(ROOT_DIR / 'packaging' / 'launcher.py')],
    pathex=[str(ROOT_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=qt_excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='comic-scroll-reader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT_DIR / 'comic_scroll_reader' / 'assets' / 'csr_app_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='comic-scroll-reader',
)
