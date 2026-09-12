"""Unit tests for asset discovery and application icon resolution across platforms."""

import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from comic_scroll_reader.core.resources import (
    APP_ICON_PATH,
    APP_NAME,
    find_app_icon_path,
    get_app_icon,
)

app = QApplication.instance()
if app is None:
    app = QApplication(["--platform", "offscreen"])


class TestResourceDiscovery(unittest.TestCase):
    """Tests for application branding and asset discovery logic."""

    def test_app_name_defined(self):
        self.assertEqual(APP_NAME, "Comic Scroll Reader")

    def test_app_icon_path_exists(self):
        self.assertTrue(APP_ICON_PATH.exists(), f"APP_ICON_PATH not found at {APP_ICON_PATH}")
        self.assertTrue(APP_ICON_PATH.is_file())

    def test_get_app_icon_non_null(self):
        icon = get_app_icon()
        self.assertIsInstance(icon, QIcon)
        self.assertFalse(icon.isNull(), "Application icon is null")
        sizes = icon.availableSizes()
        self.assertGreater(len(sizes), 0)
        # Verify both 16x16 and 32x32 standard resolutions are available
        self.assertIn(QSize(16, 16), sizes)
        self.assertIn(QSize(32, 32), sizes)

    def test_find_app_icon_path_pyinstaller_frozen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_assets = temp_path / "comic_scroll_reader" / "assets"
            fake_assets.mkdir(parents=True)
            fake_icon = fake_assets / "csr_app_icon.png"
            fake_icon.write_text("fake png")

            with patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "_MEIPASS", str(temp_path), create=True):
                resolved = find_app_icon_path()
                self.assertEqual(resolved, fake_icon)

    def test_find_app_icon_path_macos_bundle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Simulate MyApp.app/Contents/MacOS/myapp and MyApp.app/Contents/Resources/
            macos_dir = temp_path / "Contents" / "MacOS"
            macos_dir.mkdir(parents=True)
            fake_exe = macos_dir / "comic-scroll-reader"
            fake_exe.touch()

            resources_dir = temp_path / "Contents" / "Resources"
            resources_dir.mkdir(parents=True)
            fake_icon = resources_dir / "csr_app_icon.icns"
            fake_icon.write_text("fake icns")

            with patch.object(sys, "executable", str(fake_exe)):
                resolved = find_app_icon_path()
                self.assertEqual(resolved, fake_icon)

    def test_icns_file_contains_standard_and_retina_sizes(self):
        icns_path = APP_ICON_PATH.parent / "csr_app_icon.icns"
        self.assertTrue(icns_path.is_file(), "csr_app_icon.icns does not exist")
        icon = QIcon(str(icns_path))
        sizes = set((s.width(), s.height()) for s in icon.availableSizes())
        expected_sizes = {(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)}
        self.assertTrue(expected_sizes.issubset(sizes), f"Missing sizes in ICNS: {expected_sizes - sizes}")
