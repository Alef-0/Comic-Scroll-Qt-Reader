"""Unit tests for the QPainter-based image viewer."""

import os
import tempfile
import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPixmap, QColor
from PyQt6.QtCore import Qt, QSize, QRect

from src.viewer import ImageViewerWidget, ScaledImageLabel, MainWindow

# Ensure single QApplication instance across tests
app = QApplication.instance()
if app is None:
    app = QApplication(["--platform", "offscreen"])


class TestImageViewerWidget(unittest.TestCase):
    """Test suite for ImageViewerWidget."""

    def setUp(self):
        self.viewer = ImageViewerWidget()
        self.viewer.resize(800, 600)

    def tearDown(self):
        self.viewer.deleteLater()

    def test_initial_state(self):
        """Verify initial state of ImageViewerWidget."""
        self.assertIsNone(self.viewer.pixmap())
        self.assertEqual(self.viewer.minimumSize(), QSize(1, 1))
        self.assertTrue(self.viewer.target_rect().isEmpty())

    def test_set_pixmap(self):
        """Verify setting a pixmap directly."""
        img = QImage(100, 200, QImage.Format.Format_RGB32)
        pix = QPixmap.fromImage(img)
        self.viewer.set_pixmap(pix)

        self.assertIsNotNone(self.viewer.pixmap())
        self.assertEqual(self.viewer.pixmap().width(), 100)
        self.assertEqual(self.viewer.pixmap().height(), 200)

    def test_target_rect_preserves_aspect_ratio(self):
        """Verify target_rect computes correct centered dimensions."""
        # 200x100 image (2:1 aspect ratio) in 800x600 widget
        img = QImage(200, 100, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))

        rect = self.viewer.target_rect()
        # Should fit width 800, height should be 400, centered vertically at y=(600-400)/2 = 100
        self.assertEqual(rect.width(), 800)
        self.assertEqual(rect.height(), 400)
        self.assertEqual(rect.x(), 0)
        self.assertEqual(rect.y(), 100)

    def test_target_rect_tall_aspect_ratio(self):
        """Verify target_rect computes correct dimensions for tall image."""
        # 100x200 image (1:2 aspect ratio) in 800x600 widget
        img = QImage(100, 200, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))

        rect = self.viewer.target_rect()
        # Should fit height 600, width should be 300, centered horizontally at x=(800-300)/2 = 250
        self.assertEqual(rect.height(), 600)
        self.assertEqual(rect.width(), 300)
        self.assertEqual(rect.x(), 250)
        self.assertEqual(rect.y(), 0)

    def test_load_valid_and_invalid_image(self):
        """Verify image loading from disk handles valid and invalid files."""
        # Create a temporary image
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_path = f.name

        try:
            img = QImage(50, 50, QImage.Format.Format_RGB32)
            img.fill(QColor("red"))
            img.save(temp_path, "PNG")

            # Load valid image
            self.assertTrue(self.viewer.load_image(temp_path))
            self.assertIsNotNone(self.viewer.pixmap())
            self.assertEqual(self.viewer.pixmap().width(), 50)

            # Load non-existent image
            self.assertFalse(self.viewer.load_image("/non/existent/path/img.png"))
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_clear(self):
        """Verify clear() resets pixmap and path."""
        img = QImage(50, 50, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))
        self.assertIsNotNone(self.viewer.pixmap())

        self.viewer.clear()
        self.assertIsNone(self.viewer.pixmap())
        self.assertTrue(self.viewer.target_rect().isEmpty())

    def test_paint_event_renders_without_error(self):
        """Verify paintEvent executes cleanly using QPainter offscreen."""
        img = QImage(400, 300, QImage.Format.Format_RGB32)
        img.fill(QColor("blue"))
        self.viewer.set_pixmap(QPixmap.fromImage(img))

        render_target = QImage(800, 600, QImage.Format.Format_RGB32)
        self.viewer.render(render_target)
        self.assertFalse(render_target.isNull())

    def test_backwards_compatibility_alias(self):
        """Verify ScaledImageLabel is an alias of ImageViewerWidget."""
        self.assertIs(ScaledImageLabel, ImageViewerWidget)


class TestMainWindow(unittest.TestCase):
    """Test suite for MainWindow."""

    def test_main_window_init(self):
        """Verify MainWindow initializes with correct dimensions and central widget."""
        window = MainWindow()
        self.assertEqual(window.width(), MainWindow.DEFAULT_WIDTH)
        self.assertEqual(window.height(), MainWindow.DEFAULT_HEIGHT)
        self.assertIsInstance(window.viewer, ImageViewerWidget)
        self.assertIs(window.image_label, window.image_viewer)
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
