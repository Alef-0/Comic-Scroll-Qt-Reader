# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for Comic Scroll Reader on macOS."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT_DIR = Path.cwd()

datas = [
    (str(ROOT_DIR / 'comic_scroll_reader' / 'assets' / 'csr_app_icon.png'), 'comic_scroll_reader/assets'),
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

# Ensure pypdfium2 binary libraries (libpdfium.dylib) and data are bundled
for pkg in ('pypdfium2', 'pypdfium2_raw'):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Collect PyQt6 modules, plugins, and metadata
for pkg in ('PyQt6',):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    [str(ROOT_DIR / 'packaging' / 'launcher.py')],
    pathex=[str(ROOT_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy', 'pytest', 'unittest'],
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
    icon=str(ROOT_DIR / 'comic_scroll_reader' / 'assets' / 'csr_app_icon.png'),
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

app = BUNDLE(
    coll,
    name='Comic Scroll Reader.app',
    icon=str(ROOT_DIR / 'comic_scroll_reader' / 'assets' / 'csr_app_icon.png'),
    bundle_identifier='com.github.alef0.comic-scroll-reader',
    info_plist={
        'CFBundleDisplayName': 'Comic Scroll Reader',
        'CFBundleName': 'Comic Scroll Reader',
        'CFBundleIdentifier': 'com.github.alef0.comic-scroll-reader',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'PDF Document',
                'CFBundleTypeRole': 'Viewer',
                'LSHandlerRank': 'Alternate',
                'LSItemContentTypes': ['com.adobe.pdf'],
            },
            {
                'CFBundleTypeName': 'Image Document',
                'CFBundleTypeRole': 'Viewer',
                'LSHandlerRank': 'Alternate',
                'LSItemContentTypes': ['public.image'],
            },
        ],
    },
)
