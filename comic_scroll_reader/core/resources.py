import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon


APP_NAME = "Comic Scroll Reader"


def find_app_icon_path() -> Path:
    """Resolve the absolute path to the application icon across all environments.

    Search order:
    1. PyInstaller extraction / bundle directory (sys._MEIPASS).
    2. macOS .app bundle Resources directory (Contents/Resources).
    3. Python package relative assets directory.
    4. Linux standard XDG icon directories (/usr/share/icons, /usr/local/share/icons, /usr/share/pixmaps).
    """
    candidates = []

    # 1. PyInstaller frozen application directory
    if getattr(sys, "frozen", False):
        meipass_raw = getattr(sys, "_MEIPASS", None)
        if meipass_raw:
            meipass = Path(meipass_raw).resolve()
            candidates.extend([
                meipass / "comic_scroll_reader" / "assets" / "csr_app_icon.png",
                meipass / "comic_scroll_reader" / "assets" / "csr_app_icon.icns",
                meipass / "comic_scroll_reader" / "assets" / "csr_app_icon.ico",
                meipass / "assets" / "csr_app_icon.png",
                meipass / "assets" / "csr_app_icon.icns",
                meipass / "assets" / "csr_app_icon.ico",
            ])

    # 2. macOS .app bundle directory (Contents/Resources)
    try:
        exe_path = Path(sys.executable).resolve()
        # Checks if running inside an .app bundle
        bundle_contents = None
        if "Contents/MacOS" in str(exe_path):
            bundle_contents = exe_path.parent.parent
        elif exe_path.parent.name == "MacOS" and exe_path.parent.parent.name == "Contents":
            bundle_contents = exe_path.parent.parent

        if bundle_contents and bundle_contents.is_dir():
            resources_dir = bundle_contents / "Resources"
            candidates.extend([
                resources_dir / "comic_scroll_reader" / "assets" / "csr_app_icon.png",
                resources_dir / "comic_scroll_reader" / "assets" / "csr_app_icon.icns",
                resources_dir / "csr_app_icon.icns",
                resources_dir / "csr_app_icon.png",
            ])
    except Exception:
        pass

    # 3. Development checkout / normal Python package layout
    pkg_assets = Path(__file__).resolve().parent.parent / "assets"
    candidates.extend([
        pkg_assets / "csr_app_icon.png",
        pkg_assets / "csr_app_icon.icns",
        pkg_assets / "csr_app_icon.ico",
    ])

    # 4. Standard Linux installation locations
    candidates.extend([
        Path("/usr/share/icons/hicolor/512x512/apps/comic-scroll-reader.png"),
        Path("/usr/local/share/icons/hicolor/512x512/apps/comic-scroll-reader.png"),
        Path("/usr/share/pixmaps/comic-scroll-reader.png"),
    ])

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    # Return default expected path even if missing to prevent NoneType errors
    return pkg_assets / "csr_app_icon.png"


def get_app_icon() -> QIcon:
    """Return a fully populated QIcon with all available platform-native mipmaps."""
    icon_path = find_app_icon_path()
    if not icon_path.exists():
        return QIcon.fromTheme("comic-scroll-reader")

    icon = QIcon(str(icon_path))

    # Augment icon with native container formats (.icns / .ico) if available in the same assets folder
    assets_dir = icon_path.parent
    if sys.platform == "darwin":
        icns_candidate = assets_dir / "csr_app_icon.icns"
        if icns_candidate.is_file() and icns_candidate != icon_path:
            icon.addFile(str(icns_candidate))
    elif sys.platform.startswith("win"):
        ico_candidate = assets_dir / "csr_app_icon.ico"
        if ico_candidate.is_file() and ico_candidate != icon_path:
            icon.addFile(str(ico_candidate))

    # Also check .icns as a general multi-resolution format
    icns_file = assets_dir / "csr_app_icon.icns"
    if icns_file.is_file() and icns_file != icon_path and icon.availableSizes() == [QSize(512, 512)]:
        # Add rich mipmaps if only a single resolution was loaded from PNG
        icon.addFile(str(icns_file))

    return icon


APP_ICON_PATH = find_app_icon_path()

