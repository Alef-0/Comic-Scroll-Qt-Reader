"""Unit tests for ScrollReaderWidget and Scroll Reader mode in MainWindow."""

import os
import shutil
import tempfile
import unittest

from PyQt6.QtCore import QEventLoop, QObject, QPointF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication

from src.scroll_reader import ScrollReaderWidget
from src.image_pipeline import DecodeRequest, DecodeResult
from src.viewer import ImageViewerWidget, MainWindow, ViewerMode

# Ensure QApplication is initialized
app = QApplication.instance()
if app is None:
    app = QApplication(["--platform", "offscreen"])


def wait_for_signal(signal, condition, timeout_ms=3000):
    """Process Qt events until condition is met or timeout occurs."""
    if condition():
        return True
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    signal.connect(loop.quit)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    loop.exec()
    try:
        signal.disconnect(loop.quit)
    except TypeError:
        pass
    return condition()


class RecordingPipeline(QObject):
    """Deterministic pipeline double for scroll request lifecycle tests."""

    image_ready = pyqtSignal(object)
    image_failed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.requests = []
        self.promotions = []
        self.cancellations = []

    def request_preview(
        self, path, bounds, request_id, purpose="current-preview", priority=0
    ):
        self.requests.append(
            {
                "path": os.path.abspath(path),
                "bounds": QSize(bounds),
                "request_id": request_id,
                "purpose": purpose,
                "priority": priority,
            }
        )

    def promote_queued(self, path, bounds, priority):
        self.promotions.append((os.path.abspath(path), QSize(bounds), priority))
        return True

    def cancel_queued(self, purposes=None):
        self.cancellations.append(set(purposes) if purposes is not None else None)


class TestScrollReaderRequestLifecycle(unittest.TestCase):
    """Regression coverage for sharpness, priority promotion, and stale work."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.image_paths = []
        for index in range(5):
            path = os.path.join(self.temp_dir, f"page{index + 1}.png")
            image = QImage(200, 400, QImage.Format.Format_RGB32)
            image.fill(QColor("cyan"))
            image.save(path, "PNG")
            self.image_paths.append(path)

        self.pipeline = RecordingPipeline()
        self.widget = ScrollReaderWidget(pipeline=self.pipeline)
        self.widget.resize(400, 300)

    def tearDown(self):
        self.widget.deleteLater()
        shutil.rmtree(self.temp_dir)

    @staticmethod
    def result_for(record, color="cyan"):
        image = QImage(
            record["bounds"].width(),
            record["bounds"].height(),
            QImage.Format.Format_RGB32,
        )
        image.fill(QColor(color))
        request = DecodeRequest(
            request_id=record["request_id"],
            path=record["path"],
            purpose=record["purpose"],
            bounds=QSize(record["bounds"]),
            cache_key=(record["path"], record["bounds"].width()),
        )
        return DecodeResult(request, image, QSize(200, 400))

    def test_zoom_requests_larger_decode_and_keeps_sharpest_result(self):
        """A visible page refines after zoom and a late small result is ignored."""
        self.widget.set_images([self.image_paths[0]])
        small_request = self.pipeline.requests[-1]

        self.widget.set_zoom(2.0)
        large_request = self.pipeline.requests[-1]
        self.assertGreater(
            large_request["bounds"].width(), small_request["bounds"].width()
        )

        self.widget._on_image_ready(self.result_for(large_request, "green"))
        self.widget._on_image_ready(self.result_for(small_request, "red"))

        self.assertEqual(self.widget._pixmaps[0].size(), large_request["bounds"])
        self.assertEqual(self.widget._decoded_bounds[0], large_request["bounds"])

    def test_visible_prefetch_is_promoted(self):
        """A nearby low-priority request is promoted when scrolled into view."""
        self.widget.set_images(self.image_paths)
        page_two = next(
            request
            for request in self.pipeline.requests
            if request["request_id"] == 1
        )
        self.assertEqual(page_two["priority"], 0)

        self.widget.scroll_to_index(1)

        self.assertIn(
            (self.image_paths[1], page_two["bounds"], 2),
            self.pipeline.promotions,
        )

    def test_fast_scroll_cancels_distant_pending_consumers(self):
        """Pending work outside the prefetch window cannot grow across the folder."""
        self.widget.set_images(self.image_paths)
        self.widget.scroll_to_index(4)

        cancelled_purposes = set().union(*self.pipeline.cancellations)
        self.assertIn("scroll-0", cancelled_purposes)
        self.assertIn("scroll-1", cancelled_purposes)


class TestScrollReaderWidget(unittest.TestCase):
    """Test suite for ScrollReaderWidget layout, sizing, zooming, and spacing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.image_paths = []

        # Create images with diverse dimensions to test uniform width and aspect ratios
        specs = [
            ("img_01.png", 200, 400),  # Tall 1:2
            ("img_02.png", 400, 200),  # Wide 2:1
            ("img_03.png", 300, 300),  # Square 1:1
        ]
        for name, w, h in specs:
            p = os.path.join(self.temp_dir, name)
            img = QImage(w, h, QImage.Format.Format_RGB32)
            img.fill(QColor("blue"))
            img.save(p, "PNG")
            self.image_paths.append(p)

        self.widget = ScrollReaderWidget()
        self.widget.resize(800, 600)
        self.widget.set_images(self.image_paths, start_index=0)

    def tearDown(self):
        self.widget.deleteLater()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_image_ordering(self):
        """Images follow natural/alphabetical order."""
        self.assertEqual(self.widget.image_list, self.image_paths)

    def test_uniform_width_across_all_images(self):
        """All images must have the exact same width by default."""
        rects = self.widget.image_rects
        self.assertEqual(len(rects), 3)

        first_width = rects[0].width()
        self.assertGreater(first_width, 0)
        for i, rect in enumerate(rects):
            self.assertEqual(
                rect.width(),
                first_width,
                f"Image {i} width ({rect.width()}) does not match uniform width ({first_width})",
            )

    def test_aspect_ratio_preservation(self):
        """Each image must strictly preserve its individual aspect ratio."""
        rects = self.widget.image_rects
        # img_01 is 200x400 (ratio h/w = 2.0)
        ratio_0 = rects[0].height() / rects[0].width()
        self.assertAlmostEqual(ratio_0, 2.0, delta=0.02)

        # img_02 is 400x200 (ratio h/w = 0.5)
        ratio_1 = rects[1].height() / rects[1].width()
        self.assertAlmostEqual(ratio_1, 0.5, delta=0.02)

        # img_03 is 300x300 (ratio h/w = 1.0)
        ratio_2 = rects[2].height() / rects[2].width()
        self.assertAlmostEqual(ratio_2, 1.0, delta=0.02)

    def test_spacing_between_images(self):
        """There must be vertical spacing (SPACING = 10px) between consecutive images."""
        rects = self.widget.image_rects
        for i in range(len(rects) - 1):
            bottom_of_current = rects[i].y() + rects[i].height()
            top_of_next = rects[i + 1].y()
            gap = top_of_next - bottom_of_current
            self.assertEqual(
                gap,
                ScrollReaderWidget.SPACING,
                f"Gap between image {i} and {i+1} is {gap}, expected {ScrollReaderWidget.SPACING}",
            )

    def test_scroll_to_index(self):
        """scroll_to_index positions the vertical scrollbar at the image's top."""
        rects = self.widget.image_rects
        self.widget.scroll_to_index(1)
        self.assertEqual(self.widget.verticalScrollBar().value(), rects[1].y())
        self.assertEqual(self.widget.current_visible_index(), 1)

        self.widget.scroll_to_index(2)
        self.assertEqual(self.widget.verticalScrollBar().value(), rects[2].y())
        self.assertEqual(self.widget.current_visible_index(), 2)

    def test_zoom_scales_uniform_width_and_preserves_aspect_ratios(self):
        """Zooming in and out scales all images to the same width while keeping aspect ratios."""
        initial_rects = self.widget.image_rects
        initial_w = initial_rects[0].width()

        # Zoom in
        self.widget.zoom_in()
        zoomed_rects = self.widget.image_rects
        zoomed_w = zoomed_rects[0].width()
        self.assertGreater(zoomed_w, initial_w)

        # All still have the same width
        for r in zoomed_rects:
            self.assertEqual(r.width(), zoomed_w)

        # Aspect ratios still preserved
        self.assertAlmostEqual(zoomed_rects[0].height() / zoomed_rects[0].width(), 2.0, delta=0.02)
        self.assertAlmostEqual(zoomed_rects[1].height() / zoomed_rects[1].width(), 0.5, delta=0.02)

        # Reset zoom
        self.widget.reset_zoom()
        self.assertEqual(self.widget.zoom_factor, 1.0)
        self.assertEqual(self.widget.image_rects[0].width(), initial_w)

    def test_drag_to_pan(self):
        """Mouse left drag translates the vertical scrollbar."""
        initial_val = self.widget.verticalScrollBar().value()

        # Press left button
        press_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(200, 300),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.widget.mousePressEvent(press_ev)

        # Drag up by 50px (simulating scrolling down)
        move_ev = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(200, 250),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.widget.mouseMoveEvent(move_ev)
        self.assertEqual(self.widget.verticalScrollBar().value(), initial_val + 50)

        # Release
        rel_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(200, 250),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.widget.mouseReleaseEvent(rel_ev)

    def test_right_click_emits_toggle_mode(self):
        """Right click emits toggle_mode_requested."""
        emitted = []
        self.widget.toggle_mode_requested.connect(lambda: emitted.append(True))

        right_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(100, 100),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.widget.mousePressEvent(right_ev)
        self.assertEqual(emitted, [True])

    def test_key_1_and_2_emit_mode_signals(self):
        """Key 1 emits mode_single_requested, Key 2 emits mode_scroll_requested."""
        single_emitted = []
        scroll_emitted = []
        self.widget.mode_single_requested.connect(lambda: single_emitted.append(True))
        self.widget.mode_scroll_requested.connect(lambda: scroll_emitted.append(True))

        key1_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier)
        self.widget.keyPressEvent(key1_ev)
        self.assertEqual(single_emitted, [True])

        key2_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_2, Qt.KeyboardModifier.NoModifier)
        self.widget.keyPressEvent(key2_ev)
        self.assertEqual(scroll_emitted, [True])


class TestMainWindowScrollReaderMode(unittest.TestCase):
    """Test suite for MainWindow running in Scroll Reader mode and mode switching."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.image_files = []
        for name in ["page1.png", "page2.png", "page10.png"]:
            path = os.path.join(self.temp_dir, name)
            img = QImage(100, 150, QImage.Format.Format_RGB32)
            img.fill(QColor("magenta"))
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

    def test_starts_in_scroll_reader_mode(self):
        """From now on, MainWindow must start in scroll reader mode by default."""
        window = MainWindow(target_path=self.temp_dir)
        self.assert_loaded(window, 0)
        self.assertEqual(window.viewer_mode, ViewerMode.SCROLL)
        self.assertIs(window._stack.currentWidget(), window.scroll_reader)
        self.assertIn("[Scroll]", window.windowTitle())
        window.deleteLater()

    def test_scroll_starts_in_image_passed(self):
        """When opened with a specific image file, scroll reader starts positioned on that image."""
        target_file = os.path.join(self.temp_dir, "page2.png")
        window = MainWindow(image_path=target_file)
        self.assert_loaded(window, 1)

        self.assertEqual(window.current_index, 1)
        self.assertEqual(window.viewer_mode, ViewerMode.SCROLL)
        rects = window.scroll_reader.image_rects
        self.assertEqual(window.scroll_reader.verticalScrollBar().value(), rects[1].y())
        self.assertIn("page2.png", window.windowTitle())
        window.deleteLater()

    def test_toggle_mode_via_keys_1_and_2(self):
        """Key 1 switches to Single Image mode; Key 2 switches to Scroll Reader mode."""
        window = MainWindow(target_path=self.temp_dir)
        self.assert_loaded(window, 0)
        self.assertEqual(window.viewer_mode, ViewerMode.SCROLL)

        # Press Key 1 -> Switch to Single Image mode
        key1_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier)
        window.keyPressEvent(key1_ev)
        self.assertEqual(window.viewer_mode, ViewerMode.SINGLE)
        self.assertIs(window._stack.currentWidget(), window.image_viewer)
        self.assertNotIn("[Scroll]", window.windowTitle())

        # Press Key 2 -> Switch to Scroll Reader mode
        key2_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_2, Qt.KeyboardModifier.NoModifier)
        window.keyPressEvent(key2_ev)
        self.assertEqual(window.viewer_mode, ViewerMode.SCROLL)
        self.assertIs(window._stack.currentWidget(), window.scroll_reader)
        self.assertIn("[Scroll]", window.windowTitle())

        window.deleteLater()

    def test_alternate_mode_via_right_click(self):
        """Right mouse button alternates between Single Image and Scroll Reader modes."""
        window = MainWindow(target_path=self.temp_dir)
        self.assert_loaded(window, 0)
        self.assertEqual(window.viewer_mode, ViewerMode.SCROLL)

        # Right click in scroll reader -> alternates to Single Image mode
        window.toggle_mode()
        self.assertEqual(window.viewer_mode, ViewerMode.SINGLE)
        self.assertIs(window._stack.currentWidget(), window.image_viewer)

        # Right click again -> alternates back to Scroll Reader mode
        window.toggle_mode()
        self.assertEqual(window.viewer_mode, ViewerMode.SCROLL)
        self.assertIs(window._stack.currentWidget(), window.scroll_reader)

        window.deleteLater()

    def test_index_synchronization_when_switching_modes(self):
        """Active image index is bidirectionally synchronized when switching modes."""
        window = MainWindow(target_path=self.temp_dir)
        self.assert_loaded(window, 0)

        # Scroll to page2 (index 1) in scroll reader
        window.scroll_reader.scroll_to_index(1)
        self.assertEqual(window.scroll_reader.current_visible_index(), 1)

        # Switch to Single Image mode via Key 1
        key1_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier)
        window.keyPressEvent(key1_ev)
        self.assertEqual(window.viewer_mode, ViewerMode.SINGLE)
        self.assertEqual(window.current_index, 1)
        self.assertIn("page2.png", window.windowTitle())

        # Navigate to page10 (index 2) in Single Image mode
        window.next_image()
        self.assert_loaded(window, 2)
        self.assertEqual(window.current_index, 2)

        # Switch back to Scroll Reader mode via Key 2
        key2_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_2, Qt.KeyboardModifier.NoModifier)
        window.keyPressEvent(key2_ev)
        self.assertEqual(window.viewer_mode, ViewerMode.SCROLL)
        self.assertEqual(window.scroll_reader.current_visible_index(), 2)
        rects = window.scroll_reader.image_rects
        self.assertEqual(window.scroll_reader.verticalScrollBar().value(), rects[2].y())

        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
