"""Unit tests for the QPainter-based image viewer, navigation, and zoom/pan controls."""

import os
import shutil
import tempfile
import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPixmap, QColor, QKeyEvent
from PyQt6.QtCore import Qt, QSize, QRect, QPointF, QEventLoop, QTimer

from src.viewer import (
    ImageViewerWidget,
    ScaledImageLabel,
    MainWindow,
    natural_sort_key,
)
from src.image_pipeline import (
    ByteBoundedImageCache,
    CachedImage,
    DecodeRequest,
    DecodeResult,
)

# Ensure single QApplication instance across tests
app = QApplication.instance()
if app is None:
    app = QApplication(["--platform", "offscreen"])


def wait_for_signal(signal, condition, timeout_ms=3000):
    """Process Qt events until a worker result satisfies the expected state."""
    if condition():
        return True
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    signal.connect(loop.quit)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    loop.exec()
    signal.disconnect(loop.quit)
    return condition()


class TestNaturalSort(unittest.TestCase):
    """Test natural alphabetical ordering key."""

    def test_natural_sort_order(self):
        filenames = ["page10.png", "page2.png", "page1.png", "page20.png"]
        sorted_files = sorted(filenames, key=natural_sort_key)
        self.assertEqual(
            sorted_files, ["page1.png", "page2.png", "page10.png", "page20.png"]
        )

    def test_case_insensitive_natural_sort(self):
        filenames = ["Page2.png", "page1.png", "PAGE10.png"]
        sorted_files = sorted(filenames, key=natural_sort_key)
        self.assertEqual(sorted_files, ["page1.png", "Page2.png", "PAGE10.png"])


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
        self.assertEqual(self.viewer.zoom_factor, 1.0)
        self.assertEqual(self.viewer.pan_offset, QPointF(0, 0))

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
        img = QImage(200, 100, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))

        rect = self.viewer.target_rect()
        self.assertEqual(rect.width(), 800)
        self.assertEqual(rect.height(), 400)
        self.assertEqual(rect.x(), 0)
        self.assertEqual(rect.y(), 100)

    def test_target_rect_tall_aspect_ratio(self):
        """Verify target_rect computes correct dimensions for tall image."""
        img = QImage(100, 200, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))

        rect = self.viewer.target_rect()
        self.assertEqual(rect.height(), 600)
        self.assertEqual(rect.width(), 300)
        self.assertEqual(rect.x(), 250)
        self.assertEqual(rect.y(), 0)

    def test_preview_keeps_source_dimensions_separate(self):
        """A small preview preserves geometry from the original image."""
        preview = QImage(80, 60, QImage.Format.Format_RGB32)
        self.viewer.set_preview_pixmap(
            QPixmap.fromImage(preview),
            QSize(4000, 3000),
            "/tmp/example.png",
        )

        self.assertEqual(self.viewer.pixmap().size(), QSize(80, 60))
        self.assertEqual(self.viewer.source_size, QSize(4000, 3000))
        self.assertEqual(self.viewer.target_rect(), QRect(0, 0, 800, 600))

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

    def test_zoom_in_and_zoom_out_preserves_aspect_ratio(self):
        """Aspect ratio (w/h) is strictly preserved at various zoom levels."""
        img = QImage(300, 150, QImage.Format.Format_RGB32)  # 2:1 aspect ratio
        self.viewer.set_pixmap(QPixmap.fromImage(img))

        rect_initial = self.viewer.target_rect()
        self.assertAlmostEqual(rect_initial.width() / rect_initial.height(), 2.0)

        # Zoom in
        self.viewer.zoom_in()
        rect_in = self.viewer.target_rect()
        self.assertGreater(rect_in.width(), rect_initial.width())
        self.assertAlmostEqual(rect_in.width() / rect_in.height(), 2.0)

        # Zoom out
        self.viewer.zoom_out()
        self.viewer.zoom_out()
        rect_out = self.viewer.target_rect()
        self.assertLess(rect_out.width(), rect_initial.width())
        self.assertAlmostEqual(rect_out.width() / rect_out.height(), 2.0)

    def test_area_zoom_anchored_position(self):
        """Zooming in on an area keeps the point under the cursor stationary."""
        img = QImage(400, 200, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))
        # Initial fit in 800x600: 800x400, centered at (0, 100)
        anchor = QPointF(200, 200)

        # Point in image relative to rect before zoom
        rect_before = self.viewer.target_rect()
        norm_x = (anchor.x() - rect_before.x()) / rect_before.width()
        norm_y = (anchor.y() - rect_before.y()) / rect_before.height()

        # Zoom 2x at anchor
        self.viewer.zoom_at(2.0, anchor)
        rect_after = self.viewer.target_rect()

        # Check that the same normalized image point is still at anchor.x, anchor.y
        recomputed_anchor_x = rect_after.x() + norm_x * rect_after.width()
        recomputed_anchor_y = rect_after.y() + norm_y * rect_after.height()

        self.assertAlmostEqual(recomputed_anchor_x, anchor.x(), delta=1.0)
        self.assertAlmostEqual(recomputed_anchor_y, anchor.y(), delta=1.0)

    def test_pan_by_updates_target_rect(self):
        """Panning shifts target rect coordinates directly."""
        img = QImage(200, 200, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))
        rect1 = self.viewer.target_rect()

        self.viewer.pan_by(50, -30)
        rect2 = self.viewer.target_rect()
        self.assertEqual(rect2.x(), rect1.x() + 50)
        self.assertEqual(rect2.y(), rect1.y() - 30)

    def test_reset_view(self):
        """reset_view resets zoom factor to 1.0 and pan offset to 0."""
        img = QImage(200, 200, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))
        self.viewer.zoom_in()
        self.viewer.pan_by(100, 100)
        self.assertNotEqual(self.viewer.zoom_factor, 1.0)

        self.viewer.reset_view()
        self.assertEqual(self.viewer.zoom_factor, 1.0)
        self.assertEqual(self.viewer.pan_offset, QPointF(0, 0))

    def test_zoom_requests_full_resolution_after_interaction(self):
        """Zooming beyond available preview pixels requests the original once settled."""
        preview = QImage(800, 400, QImage.Format.Format_RGB32)
        self.viewer.set_preview_pixmap(
            QPixmap.fromImage(preview),
            QSize(4000, 2000),
            "/tmp/example.png",
        )
        requests = []
        self.viewer.full_resolution_requested.connect(lambda: requests.append(True))

        self.viewer.zoom_in()
        self.viewer._finish_interaction()

        self.assertEqual(requests, [True])


class TestByteBoundedImageCache(unittest.TestCase):
    """Verify decoded-memory accounting and least-recently-used eviction."""

    def test_cache_evicts_by_decoded_bytes(self):
        image_a = QImage(4, 4, QImage.Format.Format_ARGB32)
        image_b = QImage(4, 4, QImage.Format.Format_ARGB32)
        cache = ByteBoundedImageCache(int(image_a.sizeInBytes()))
        cache.put(("a",), CachedImage(image_a, image_a.size()))
        cache.put(("b",), CachedImage(image_b, image_b.size()))

        self.assertIsNone(cache.get(("a",)))
        self.assertIsNotNone(cache.get(("b",)))
        self.assertLessEqual(cache.bytes_used, cache.byte_limit)


class TestMainWindow(unittest.TestCase):
    """Test suite for MainWindow."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.image_files = []
        for name in ["page10.png", "page1.png", "page2.png"]:
            path = os.path.join(self.temp_dir, name)
            img = QImage(100, 100, QImage.Format.Format_RGB32)
            img.fill(QColor("green"))
            img.save(path, "PNG")
            self.image_files.append(path)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def assert_loaded(self, window, expected_index):
        self.assertTrue(
            wait_for_signal(
                window.image_loaded,
                lambda: window.current_index == expected_index
                and window.image_viewer.pixmap() is not None,
            ),
            "Timed out waiting for asynchronous image decoding",
        )

    def test_main_window_init(self):
        """Verify MainWindow initializes with correct dimensions and central widget."""
        window = MainWindow()
        self.assertEqual(window.width(), MainWindow.DEFAULT_WIDTH)
        self.assertEqual(window.height(), MainWindow.DEFAULT_HEIGHT)
        self.assertIsInstance(window.viewer, ImageViewerWidget)
        self.assertIs(window.image_label, window.image_viewer)
        window.deleteLater()

    def test_folder_discovery_and_alphabetical_order(self):
        """Verify images in folder are discovered and sorted alphabetically (page1, page2, page10)."""
        window = MainWindow(target_path=self.temp_dir)
        self.assert_loaded(window, 0)
        self.assertEqual(len(window.image_list), 3)
        self.assertTrue(window.image_list[0].endswith("page1.png"))
        self.assertTrue(window.image_list[1].endswith("page2.png"))
        self.assertTrue(window.image_list[2].endswith("page10.png"))
        self.assertEqual(window.current_index, 0)
        self.assertIn("[1/3]", window.windowTitle())
        self.assertIn("page1.png", window.windowTitle())
        window.deleteLater()

    def test_navigation_and_counter_updating(self):
        """Verify next_image and prev_image update the title counter and clamp at bounds."""
        window = MainWindow(target_path=self.temp_dir)
        self.assert_loaded(window, 0)

        # Initially at page1 (1/3)
        self.assertEqual(window.current_index, 0)
        self.assertIn("[1/3]", window.windowTitle())

        # Next -> page2 (2/3)
        window.next_image()
        self.assert_loaded(window, 1)
        self.assertEqual(window.current_index, 1)
        self.assertIn("[2/3]", window.windowTitle())

        # Next -> page10 (3/3)
        window.next_image()
        self.assert_loaded(window, 2)
        self.assertEqual(window.current_index, 2)
        self.assertIn("[3/3]", window.windowTitle())

        # Next again clamps at page10 (3/3)
        window.next_image()
        self.assertEqual(window.current_index, 2)
        self.assertIn("[3/3]", window.windowTitle())

        # Prev -> page2 (2/3)
        window.prev_image()
        self.assert_loaded(window, 1)
        self.assertEqual(window.current_index, 1)
        self.assertIn("[2/3]", window.windowTitle())

        # First and Last methods
        window.last_image()
        self.assert_loaded(window, 2)
        self.assertEqual(window.current_index, 2)
        window.first_image()
        self.assert_loaded(window, 0)
        self.assertEqual(window.current_index, 0)
        window.deleteLater()

    def test_initial_file_selects_correct_index(self):
        """Opening a specific file in a folder sets current_index to that file."""
        target_file = os.path.join(self.temp_dir, "page2.png")
        window = MainWindow(image_path=target_file)
        self.assert_loaded(window, 1)
        self.assertEqual(window.current_index, 1)
        self.assertIn("[2/3]", window.windowTitle())
        self.assertIn("page2.png", window.windowTitle())
        window.deleteLater()

    def test_empty_directory(self):
        """Opening an empty directory displays [0/0] No images found."""
        empty_dir = tempfile.mkdtemp()
        try:
            window = MainWindow(target_path=empty_dir)
            self.assertEqual(len(window.image_list), 0)
            self.assertIn("[0/0]", window.windowTitle())
            window.deleteLater()
        finally:
            shutil.rmtree(empty_dir)

    def test_keyboard_events_in_main_window(self):
        """Verify MainWindow keyPressEvent triggers navigation and zoom."""
        window = MainWindow(target_path=self.temp_dir)
        self.assert_loaded(window, 0)
        self.assertEqual(window.current_index, 0)

        # Key Right -> Next
        event_right = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
        window.keyPressEvent(event_right)
        self.assert_loaded(window, 1)
        self.assertEqual(window.current_index, 1)

        # Ctrl+Plus -> Zoom In
        initial_zoom = window.image_viewer.zoom_factor
        event_zoom = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
        window.keyPressEvent(event_zoom)
        self.assertGreater(window.image_viewer.zoom_factor, initial_zoom)
        window.deleteLater()

    def test_failed_navigation_keeps_displayed_index_and_title(self):
        """A corrupt target never commits its index over the valid displayed image."""
        window = MainWindow(target_path=self.temp_dir)
        self.assert_loaded(window, 0)
        corrupt_path = window.image_list[1]
        with open(corrupt_path, "wb") as corrupt_file:
            corrupt_file.write(b"not an image")

        window.go_to_index(1)
        self.assertTrue(
            wait_for_signal(
                window.image_load_failed,
                lambda: window._requested_index is None,
            )
        )

        self.assertEqual(window.current_index, 0)
        self.assertIn("page1.png", window.windowTitle())
        window.deleteLater()

    def test_stale_decode_result_cannot_replace_newer_request(self):
        """A late worker result is ignored after the request generation advances."""
        window = MainWindow()
        current_path = os.path.abspath(self.image_files[0])
        requested_path = os.path.abspath(self.image_files[1])
        window.image_list = [current_path, requested_path]
        window.current_index = 0
        window._requested_index = 1
        window._request_generation = 2

        current_preview = QImage(20, 20, QImage.Format.Format_RGB32)
        window.image_viewer.set_preview_pixmap(
            QPixmap.fromImage(current_preview), QSize(100, 100), current_path
        )
        stale_request = DecodeRequest(
            request_id=1,
            path=requested_path,
            purpose="current-preview",
            bounds=QSize(800, 600),
            cache_key=(requested_path, "stale"),
        )
        stale_image = QImage(30, 30, QImage.Format.Format_RGB32)
        window._on_image_ready(
            DecodeResult(stale_request, stale_image, QSize(100, 100))
        )

        self.assertEqual(window.current_index, 0)
        self.assertEqual(window._requested_index, 1)
        self.assertEqual(window.image_viewer.image_path, current_path)
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
