"""Unit tests for the QPainter-based image viewer, navigation, and zoom/pan controls."""

import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import (
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPixmap,
    QWheelEvent,
)
from PyQt6.QtCore import Qt, QSize, QRect, QPoint, QPointF, QEventLoop, QTimer

from comic_scroll_reader.main_window import (
    ImageViewerWidget,
    ScaledImageLabel,
    MainWindow,
    ViewerMode,
    natural_sort_key,
)
from comic_scroll_reader.image_pipeline import (
    ByteBoundedImageCache,
    CachedImage,
    DecodeRequest,
    DecodeResult,
    ImagePipeline,
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

    def _make_wheel(self, delta_y, modifiers=Qt.KeyboardModifier.NoModifier):
        return QWheelEvent(
            QPointF(200, 200),
            QPointF(200, 200),
            QPoint(),
            QPoint(0, delta_y),
            Qt.MouseButton.NoButton,
            modifiers,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )

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

    def test_mouse_position_does_not_decenter_zoom(self):
        """Single-view zoom remains centred regardless of the mouse position."""
        img = QImage(400, 200, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))
        anchor = QPointF(200, 200)

        self.viewer.zoom_at(2.0, anchor)
        rect_after = self.viewer.target_rect()

        self.assertAlmostEqual(
            rect_after.x() + rect_after.width() / 2.0,
            self.viewer.width() / 2.0,
            delta=1.0,
        )
        self.assertAlmostEqual(
            rect_after.y() + rect_after.height() / 2.0,
            self.viewer.height() / 2.0,
            delta=1.0,
        )

    def test_fit_image_cannot_be_panned(self):
        """An image contained by the viewport remains centred when dragged."""
        img = QImage(200, 200, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))
        rect1 = self.viewer.target_rect()

        self.viewer.pan_by(50, -30)

        self.assertEqual(self.viewer.target_rect(), rect1)
        self.assertEqual(self.viewer.pan_offset, QPointF(0, 0))

    def test_pan_is_clamped_and_non_overflowing_axis_stays_centred(self):
        """Dragging cannot expose canvas, and a fitting axis does not move."""
        img = QImage(400, 200, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))
        self.viewer.zoom_in()  # 1000x500 in an 800x600 viewport

        self.viewer.pan_by(1000, 1000)
        rect = self.viewer.target_rect()

        self.assertEqual(self.viewer.pan_offset, QPointF(100, 0))
        self.assertEqual(rect.x(), 0)
        self.assertEqual(rect.y(), 50)

        self.viewer.pan_by(-2000, -2000)
        rect = self.viewer.target_rect()
        self.assertEqual(self.viewer.pan_offset, QPointF(-100, 0))
        self.assertEqual(rect.x() + rect.width(), self.viewer.width())

    def test_zooming_back_to_fit_recentres_image(self):
        """Zooming out clears pan once the image fits the viewport again."""
        img = QImage(400, 200, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))
        self.viewer.zoom_at(2.0, QPointF(100, 100))
        self.viewer.pan_by(200, 100)

        self.viewer.zoom_at(0.5, QPointF(700, 500))

        self.assertEqual(self.viewer.zoom_factor, 1.0)
        self.assertEqual(self.viewer.pan_offset, QPointF(0, 0))
        self.assertEqual(self.viewer.target_rect(), QRect(0, 100, 800, 400))

    def test_zoomed_wheel_pans_vertically_then_requests_next_page_at_edge(self):
        image = QImage(400, 800, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(image))
        self.viewer.zoom_at(2.0)
        transitions = []
        self.viewer.page_scroll_requested.connect(
            lambda *args: transitions.append(args)
        )

        self.viewer.wheelEvent(self._make_wheel(-120))
        self.assertEqual(self.viewer.pan_offset.y(), -80.0)
        self.assertEqual(transitions, [])

        self.viewer.pan_by(0.0, -10000.0)
        self.viewer.wheelEvent(self._make_wheel(-120))
        self.assertEqual(transitions[0][0], 1)
        self.assertEqual(transitions[0][1], 2.0)

    def test_shift_wheel_pans_horizontally_while_zoomed(self):
        image = QImage(800, 400, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(image))
        self.viewer.zoom_at(2.0)

        self.viewer.wheelEvent(
            self._make_wheel(-120, Qt.KeyboardModifier.ShiftModifier)
        )

        self.assertEqual(self.viewer.zoom_factor, 2.0)
        self.assertEqual(self.viewer.pan_offset.x(), -80.0)

    def test_ctrl_wheel_still_zooms_while_zoomed(self):
        image = QImage(800, 400, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(image))
        self.viewer.zoom_at(2.0)

        self.viewer.wheelEvent(
            self._make_wheel(-120, Qt.KeyboardModifier.ControlModifier)
        )

        self.assertEqual(self.viewer.zoom_factor, 1.6)

    def test_scroll_transition_restores_zoom_horizontal_area_and_page_edge(self):
        image = QImage(800, 800, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(image))

        self.viewer.restore_scroll_position(2.0, 0.5, at_top=True)

        limits = self.viewer._pan_limits()
        self.assertEqual(self.viewer.zoom_factor, 2.0)
        self.assertEqual(self.viewer.pan_offset.x(), limits.x() * 0.5)
        self.assertEqual(self.viewer.pan_offset.y(), limits.y())

    def test_left_drag_only_activates_when_image_overflows(self):
        """The single viewer does not enter dragging state at fit size."""
        img = QImage(400, 200, QImage.Format.Format_RGB32)
        self.viewer.set_pixmap(QPixmap.fromImage(img))
        press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(100, 100),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.viewer.mousePressEvent(press)
        self.assertFalse(self.viewer._controls.is_dragging)

        self.viewer.zoom_in()
        self.viewer.mousePressEvent(press)
        self.assertTrue(self.viewer._controls.is_dragging)

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
        """Zooming beyond available preview pixels requests more detail once settled."""
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

    def test_detail_decode_is_capped_by_byte_budget(self):
        preview = QImage(800, 800, QImage.Format.Format_RGB32)
        self.viewer.set_preview_pixmap(
            QPixmap.fromImage(preview),
            QSize(30000, 30000),
            "/tmp/large.png",
        )

        self.viewer.zoom_at(self.viewer.MAX_ZOOM)
        bounds = self.viewer.detail_bounds()

        self.assertLessEqual(
            bounds.width() * bounds.height() * 4,
            self.viewer.DETAIL_BUFFER_BYTES,
        )


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

    def test_cache_keeps_one_covering_preview_per_file(self):
        path = "/tmp/page.png"
        signature = (1, 1)
        source_size = QSize(400, 800)
        small = QImage(60, 120, QImage.Format.Format_ARGB32)
        large = QImage(80, 160, QImage.Format.Format_ARGB32)
        cache = ByteBoundedImageCache(int(large.sizeInBytes()) * 2)

        cache.put(
            (path, signature, (60, 120)), CachedImage(small, source_size)
        )
        cache.put(
            (path, signature, (80, 160)), CachedImage(large, source_size)
        )
        cache.put(
            (path, signature, (60, 120)), CachedImage(small, source_size)
        )

        cached = cache.get_covering_preview(path, signature, QSize(60, 120))
        self.assertIsNotNone(cached)
        self.assertEqual(cached.image.size(), large.size())
        self.assertEqual(cache.bytes_used, int(large.sizeInBytes()))


class TestImagePipelineCancellation(unittest.TestCase):
    """Ensure one viewer cannot strand another viewer's shared requests."""

    def test_scoped_cancel_preserves_scroll_consumer(self):
        pipeline = ImagePipeline()
        cache_key = ("/tmp/page.png", (1, 1), (800, 1200))
        current_request = DecodeRequest(
            1,
            "/tmp/page.png",
            "current-preview",
            QSize(800, 1200),
            cache_key,
        )
        scroll_request = DecodeRequest(
            0,
            "/tmp/page.png",
            "scroll-0",
            QSize(800, 1200),
            cache_key,
        )
        worker = SimpleNamespace(request=current_request)
        pipeline._workers[1] = worker
        pipeline._inflight_waiters[cache_key] = [current_request, scroll_request]
        pipeline._worker_ids_by_cache_key[cache_key] = 1
        pipeline._worker_priorities[1] = 2

        pipeline.cancel_queued({"current-preview"})

        self.assertIn(1, pipeline._workers)
        self.assertEqual(pipeline._inflight_waiters[cache_key], [scroll_request])

    def test_cancelled_running_result_is_not_cached(self):
        pipeline = ImagePipeline()
        cache_key = ("/tmp/page.png", (1, 1), (40, 40))
        request = DecodeRequest(
            1,
            "/tmp/page.png",
            "current-preview",
            QSize(40, 40),
            cache_key,
        )
        pipeline._inflight_waiters[cache_key] = []
        image = QImage(40, 40, QImage.Format.Format_ARGB32)

        pipeline._on_finished(
            1, DecodeResult(request, image, QSize(40, 40))
        )

        self.assertEqual(pipeline.preview_cache.bytes_used, 0)


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

    def test_scroll_page_transition_preserves_single_view_position(self):
        window = MainWindow(target_path=self.temp_dir)
        self.assert_loaded(window, 0)
        window.set_mode(ViewerMode.SINGLE)

        window._scroll_single_page(1, 2.0, 0.5)
        self.assert_loaded(window, 1)

        limits = window.image_viewer._pan_limits()
        self.assertEqual(window.image_viewer.zoom_factor, 2.0)
        self.assertAlmostEqual(
            window.image_viewer.pan_offset.x(), limits.x() * 0.5
        )
        self.assertEqual(window.image_viewer.pan_offset.y(), limits.y())
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
