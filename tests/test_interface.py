"""Unit tests for the MVP interface: Drag-and-Drop, WelcomeWidget, ViewerHud, MenuBar, and Navigation."""

import os
import shutil
import tempfile
import unittest
from PyQt6.QtCore import QMimeData, QPointF, QSize, Qt, QUrl, QEvent
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage, QKeyEvent
from PyQt6.QtWidgets import QApplication, QLabel

from comic_scroll_reader.__main__ import parse_arguments
from comic_scroll_reader.about_dialog import AboutDialog
from comic_scroll_reader.hud_overlay import ViewerHud
from comic_scroll_reader.main_window import ComicMode, MainWindow, ViewerMode
from comic_scroll_reader.shortcuts_dialog import ShortcutsDialog
from comic_scroll_reader.welcome_widget import WelcomeWidget

app = QApplication.instance()
if app is None:
    app = QApplication(["--platform", "offscreen"])


class TestArgumentParser(unittest.TestCase):
    """Test CLI argument parsing for standalone application launching."""

    def test_optional_argument_defaults_to_none(self):
        args = parse_arguments([])
        self.assertIsNone(args.image_path)

    def test_argument_parsed_when_provided(self):
        args = parse_arguments(["/some/path/comic.pdf"])
        self.assertEqual(args.image_path, "/some/path/comic.pdf")


class TestWelcomeWidget(unittest.TestCase):
    """Test suite for Welcome / Empty state widget."""

    def setUp(self):
        self.widget = WelcomeWidget()

    def tearDown(self):
        self.widget.deleteLater()

    def test_initial_state(self):
        self.assertFalse(self.widget._drag_hover)
        self.assertIsNotNone(self.widget.btn_open_file)
        self.assertIsNotNone(self.widget.btn_open_folder)
        self.assertTrue(self.widget.autoFillBackground())
        self.assertEqual(self.widget.palette().window().color().name(), "#17191f")
        self.assertIn("QLabel { background: transparent; }", self.widget.styleSheet())
        hero_icon = self.widget.findChild(QLabel, "heroIcon")
        self.assertIsNotNone(hero_icon.pixmap())
        self.assertFalse(hero_icon.pixmap().isNull())

    def test_drag_hover_state_change(self):
        self.widget.set_drag_hover(True)
        self.assertTrue(self.widget._drag_hover)
        self.assertIn("#1d2a3b", self.widget.card.styleSheet())
        self.assertIn("border: none", self.widget.card.styleSheet())

        self.widget.set_drag_hover(False)
        self.assertFalse(self.widget._drag_hover)
        self.assertIn("background-color: transparent", self.widget.card.styleSheet())
        self.assertIn("border: none", self.widget.card.styleSheet())

    def test_signals_emitted_on_click(self):
        file_requested = False
        folder_requested = False

        def on_file():
            nonlocal file_requested
            file_requested = True

        def on_folder():
            nonlocal folder_requested
            folder_requested = True

        self.widget.open_file_requested.connect(on_file)
        self.widget.open_folder_requested.connect(on_folder)

        self.widget.btn_open_file.click()
        self.assertTrue(file_requested)

        self.widget.btn_open_folder.click()
        self.assertTrue(folder_requested)

    def test_about_button_and_acknowledgements_label(self):
        about_requested = False

        def on_about():
            nonlocal about_requested
            about_requested = True

        self.widget.about_requested.connect(on_about)
        self.widget.btn_about.click()
        self.assertTrue(about_requested)

        self.assertEqual(
            self.widget.acknowledgements_label.text(),
            "Vibe coded by Alef_0 through Gemini and ChatGPT",
        )
        self.assertEqual(self.widget.acknowledgements_label.objectName(), "acknowledgements")
        self.assertIn(
            "QLabel#acknowledgements { color: #ffffff",
            self.widget.styleSheet(),
        )

    def test_content_stays_packed_above_remaining_space(self):
        layout = self.widget.layout()
        self.assertEqual(layout.stretch(layout.indexOf(self.widget.card)), 0)
        self.assertEqual(layout.stretch(layout.count() - 1), 1)


class TestAboutDialog(unittest.TestCase):
    """Test the custom About dialog's content and controls."""

    def test_project_stack_and_acknowledgements_are_present(self):
        dialog = AboutDialog()
        label_text = " ".join(label.text() for label in dialog.findChildren(QLabel))
        self.assertIn("Python 3", label_text)
        self.assertIn("PyQt6", label_text)
        self.assertIn("pypdfium2", label_text)
        self.assertIn("Vibe coded by Alef_0 through Gemini and ChatGPT", label_text)
        self.assertEqual(dialog.windowTitle(), "About Comic Scroll Reader")
        dialog.deleteLater()


class TestViewerHud(unittest.TestCase):
    """Test suite for ViewerHud floating bottom overlay."""

    def setUp(self):
        self.hud = ViewerHud()
        self.hud.resize(400, 48)

    def tearDown(self):
        self.hud.deleteLater()

    def test_page_info_updates_labels_and_buttons(self):
        # Middle page: previous and next navigation buttons enabled
        self.hud.set_page_info(current_index=5, total_pages=10)
        self.assertEqual(self.hud.btn_page.text(), "Page 6 / 10")
        self.assertTrue(self.hud.btn_prev.isEnabled())
        self.assertTrue(self.hud.btn_next.isEnabled())

        # First page: Previous disabled
        self.hud.set_page_info(current_index=0, total_pages=10)
        self.assertEqual(self.hud.btn_page.text(), "Page 1 / 10")
        self.assertFalse(self.hud.btn_prev.isEnabled())
        self.assertTrue(self.hud.btn_next.isEnabled())

        # Last page: Next disabled
        self.hud.set_page_info(current_index=9, total_pages=10)
        self.assertEqual(self.hud.btn_page.text(), "Page 10 / 10")
        self.assertTrue(self.hud.btn_prev.isEnabled())
        self.assertFalse(self.hud.btn_next.isEnabled())

        # Empty pages
        self.hud.set_page_info(current_index=-1, total_pages=0)
        self.assertEqual(self.hud.btn_page.text(), "Page 0 / 0")
        self.assertFalse(self.hud.btn_prev.isEnabled())
        self.assertFalse(self.hud.btn_next.isEnabled())

    def test_page_info_reserves_space_for_multi_digit_counts(self):
        self.hud.set_page_info(current_index=8, total_pages=125)
        expected_width = self.hud.btn_page.fontMetrics().horizontalAdvance(
            "Page 125 / 125"
        )
        self.assertGreaterEqual(self.hud.btn_page.minimumWidth(), expected_width)

    def test_mode_and_zoom_display(self):
        self.assertEqual(
            self.hud.btn_comic_mode.text(),
            ViewerHud.COMIC_MODE_LABELS["custom"],
        )

        self.hud.set_mode(is_scroll=True)
        self.assertIn("Scroll", self.hud.btn_mode.text())

        self.hud.set_mode(is_scroll=False)
        self.assertIn("Single", self.hud.btn_mode.text())

        self.hud.set_zoom(1.5)
        self.assertEqual(self.hud.btn_zoom_label.text(), "150%")

    def test_comic_mode_selector_and_choices_keep_one_width(self):
        selector_width = self.hud.btn_comic_mode.width()
        self.assertEqual(self.hud._comic_menu.width(), selector_width)

        for mode in ("comics", "manga", "webtoon", "custom"):
            self.hud.set_comic_mode(mode)
            self.assertEqual(self.hud.btn_comic_mode.width(), selector_width)

        self.assertEqual(
            [action.text() for action in self.hud._comic_menu.actions()],
            ["📚 Comics", "📖 Manga", "📱 Webtoon"],
        )

    def test_fullscreen_display(self):
        self.hud.set_fullscreen(True)
        self.assertEqual(self.hud.btn_fullscreen.text(), "🗗")

        self.hud.set_fullscreen(False)
        self.assertEqual(self.hud.btn_fullscreen.text(), "⛶")

    def test_reposition(self):
        self.hud.reposition(parent_width=1280, parent_height=720)
        w = self.hud.width()
        expected_x = (1280 - w) // 2
        self.assertEqual(self.hud.x(), expected_x)
        self.assertGreater(self.hud.y(), 0)

    def test_hud_button_signals(self):
        signals = []
        self.hud.prev_clicked.connect(lambda: signals.append("prev"))
        self.hud.next_clicked.connect(lambda: signals.append("next"))
        self.hud.jump_clicked.connect(lambda: signals.append("jump"))
        self.hud.mode_toggled.connect(lambda: signals.append("mode"))
        self.hud.zoom_in_clicked.connect(lambda: signals.append("zoom_in"))
        self.hud.zoom_out_clicked.connect(lambda: signals.append("zoom_out"))
        self.hud.zoom_reset_clicked.connect(lambda: signals.append("zoom_reset"))
        self.hud.fullscreen_toggled.connect(lambda: signals.append("fullscreen"))

        self.hud.btn_prev.click()
        self.hud.btn_next.click()
        self.hud.btn_page.click()
        self.hud.btn_mode.click()
        self.hud.btn_zoom_in.click()
        self.hud.btn_zoom_out.click()
        self.hud.btn_zoom_label.click()
        self.hud.btn_fullscreen.click()

        self.assertEqual(
            signals,
            [
                "prev",
                "next",
                "jump",
                "mode",
                "zoom_in",
                "zoom_out",
                "zoom_reset",
                "fullscreen",
            ],
        )

    def test_hud_only_reveals_inside_its_vertical_activation_band(self):
        self.hud.reposition(parent_width=1280, parent_height=720)
        self.hud.hide()

        self.hud.on_pointer_move(0)
        self.assertTrue(self.hud.isHidden())

        self.hud.on_pointer_move(self.hud.y())
        self.assertFalse(self.hud.isHidden())

        self.hud.on_pointer_move(0)
        self.assertFalse(self.hud._is_pointer_in_activation_band)
        self.assertTrue(self.hud._hide_timer.isActive())

    def test_hud_uses_fades_in_both_directions(self):
        self.hud.hide_immediately()
        self.hud.toggle_visibility()
        self.assertEqual(self.hud._fade_animation.endValue(), 1.0)

        self.hud.toggle_visibility()
        self.assertEqual(self.hud._fade_animation.endValue(), 0.0)

    def test_comic_mode_selector_emits_selected_preset(self):
        selected = []
        self.hud.comic_mode_selected.connect(selected.append)

        self.hud.btn_comic_mode.menu().actions()[1].trigger()

        self.assertEqual(selected, ["manga"])


class TestShortcutsDialog(unittest.TestCase):
    def test_shortcuts_use_the_application_card_style_and_current_gestures(self):
        dialog = ShortcutsDialog()
        label_text = " ".join(
            label.text() for label in dialog.findChildren(QLabel)
        )

        self.assertEqual(dialog.objectName(), "shortcutsDialog")
        self.assertIn("QFrame#shortcutCard", dialog.styleSheet())
        self.assertIn("Ctrl + Wheel", label_text)
        self.assertIn("Shift + Wheel", label_text)
        dialog.deleteLater()


class TestMainWindowInterface(unittest.TestCase):
    """Test suite for MainWindow interface, drag-and-drop, menus, and controls."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.image_files = []
        for name in ["cover.png", "p01.jpg", "p02.png"]:
            path = os.path.join(self.temp_dir, name)
            img = QImage(100, 150, QImage.Format.Format_RGB32)
            img.fill(QColor("blue"))
            img.save(path)
            self.image_files.append(path)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _make_drag_event(self, path: str) -> QDragEnterEvent:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        ev = QDragEnterEvent(
            QPointF(100, 100).toPoint(),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        ev._mime = mime
        return ev

    def _make_drop_event(self, path: str) -> QDropEvent:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        ev = QDropEvent(
            QPointF(100, 100),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        ev._mime = mime
        return ev

    def test_starts_on_welcome_widget_when_no_path(self):
        """MainWindow without arguments starts displaying WelcomeWidget."""
        window = MainWindow()
        self.assertIs(window._stack.currentWidget(), window.welcome_widget)
        self.assertEqual(window.image_list, [])
        self.assertEqual(window.current_index, -1)
        self.assertEqual(window.size().width(), window.DEFAULT_WIDTH)
        self.assertEqual(window.size().height(), window.DEFAULT_HEIGHT)
        self.assertFalse(window.windowIcon().isNull())
        self.assertIn("No images found", window.windowTitle())
        self.assertFalse(window._hud.isVisible())
        window.deleteLater()

    def test_drag_supported_and_unsupported_files(self):
        """Drag validation accepts images/folders and rejects unsupported files."""
        window = MainWindow()

        # Valid image file
        self.assertTrue(window._is_supported_drag_path(self.image_files[0]))

        # Valid folder
        self.assertTrue(window._is_supported_drag_path(self.temp_dir))

        # Unsupported extension
        unsupported_file = os.path.join(self.temp_dir, "document.txt")
        with open(unsupported_file, "w") as f:
            f.write("text content")
        self.assertFalse(window._is_supported_drag_path(unsupported_file))

        # Non-existent file
        self.assertFalse(window._is_supported_drag_path("/path/to/nonexistent.png"))

        # Drag enter event on image accepted
        drag_img = self._make_drag_event(self.image_files[0])
        window.dragEnterEvent(drag_img)
        self.assertTrue(drag_img.isAccepted())

        # Drag enter event on unsupported file ignored
        drag_txt = self._make_drag_event(unsupported_file)
        window.dragEnterEvent(drag_txt)
        self.assertFalse(drag_txt.isAccepted())

        window.deleteLater()

    def test_drop_folder_loads_images_and_switches_to_scroll_mode(self):
        """Dropping a folder loads all images and switches stack from welcome widget to scroll reader."""
        window = MainWindow()
        self.assertIs(window._stack.currentWidget(), window.welcome_widget)

        drop_ev = self._make_drop_event(self.temp_dir)
        window.dropEvent(drop_ev)

        self.assertEqual(len(window.image_list), 3)
        self.assertIs(window._stack.currentWidget(), window.scroll_reader)
        self.assertIn("cover.png", window.windowTitle())
        window.deleteLater()

    def test_drop_image_loads_folder_and_positions_on_image(self):
        """Dropping a specific image discovers siblings and selects the dropped image."""
        window = MainWindow()
        target = self.image_files[1]  # p01.jpg

        drop_ev = self._make_drop_event(target)
        window.dropEvent(drop_ev)

        self.assertEqual(len(window.image_list), 3)
        self.assertEqual(window.current_index, 1)
        self.assertIn("p01.jpg", window.windowTitle())
        window.deleteLater()

    def test_close_current_returns_to_welcome_widget(self):
        """Calling close_current clears state and displays welcome widget."""
        window = MainWindow(target_path=self.temp_dir)
        self.assertEqual(len(window.image_list), 3)
        self.assertIs(window._stack.currentWidget(), window.scroll_reader)

        window.close_current()
        self.assertEqual(len(window.image_list), 0)
        self.assertEqual(window.current_index, -1)
        self.assertIs(window._stack.currentWidget(), window.welcome_widget)
        self.assertIn("No images found", window.windowTitle())
        self.assertFalse(window._hud.isVisible())
        window.deleteLater()

    def test_menubar_structure_and_actions(self):
        """Verify menu order and the added comic layouts."""
        window = MainWindow()
        menubar = window.menuBar()
        actions = [action.text() for action in menubar.actions()]
        self.assertIn("&File", actions)
        self.assertIn("&View", actions)
        self.assertIn("&Comic Modes", actions)
        self.assertIn("&Navigate", actions)
        self.assertIn("&Help", actions)

        view_actions = [
            action.text()
            for action in menubar.actions()[1].menu().actions()
            if not action.isSeparator()
        ]
        self.assertLess(
            view_actions.index("Single &Page Mode"),
            view_actions.index("Continuous &Scroll Mode"),
        )
        self.assertTrue(window._double_spread_action.isChecked())
        window.deleteLater()

    def test_comic_mode_presets_coordinate_layout_and_hud(self):
        window = MainWindow(target_path=self.temp_dir)

        window.set_comic_mode(ComicMode.COMICS)
        self.assertTrue(window.scroll_reader.double_page)
        self.assertFalse(window.scroll_reader.invert_page_order)
        self.assertTrue(window.scroll_reader.page_spacing)
        self.assertIn("Comics", window._hud.btn_comic_mode.text())

        window.set_comic_mode(ComicMode.MANGA)
        self.assertTrue(window.scroll_reader.double_page)
        self.assertTrue(window.scroll_reader.invert_page_order)
        self.assertIn("Manga", window._hud.btn_comic_mode.text())

        window.scroll_reader.zoom_in()
        window.set_comic_mode(ComicMode.WEBTOON)
        self.assertEqual(window.viewer_mode, ViewerMode.SCROLL)
        self.assertFalse(window.scroll_reader.double_page)
        self.assertFalse(window.scroll_reader.page_spacing)
        self.assertEqual(window.scroll_reader.zoom_factor, 1.0)
        self.assertIn("Webtoon", window._hud.btn_comic_mode.text())
        window.deleteLater()

    def test_toggle_fullscreen(self):
        """Fullscreen toggle switches fullscreen state and updates HUD."""
        window = MainWindow()
        self.assertFalse(window.isFullScreen())

        window.toggle_fullscreen()
        self.assertTrue(window.isFullScreen())
        self.assertFalse(window.menuBar().isVisible())
        self.assertEqual(window._hud.btn_fullscreen.text(), "🗗")

        window.toggle_fullscreen()
        self.assertFalse(window.isFullScreen())
        self.assertTrue(window.menuBar().isVisible())
        self.assertEqual(window._hud.btn_fullscreen.text(), "⛶")
        window.deleteLater()

    def test_hud_visibility_toggle(self):
        """Pressing H alternates the HUD's intended visibility."""
        window = MainWindow(target_path=self.temp_dir)
        window._hud.hide_immediately()
        key_h = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_H,
            Qt.KeyboardModifier.NoModifier,
        )
        self.assertFalse(window._hud._fade_target_visible)
        window.keyPressEvent(key_h)
        self.assertTrue(window._hud._fade_target_visible)
        self.assertFalse(window._hud.isHidden())
        window.keyPressEvent(key_h)
        self.assertFalse(window._hud._fade_target_visible)
        window.deleteLater()

    def test_close_current_restores_normal_default_window_from_fullscreen(self):
        window = MainWindow(target_path=self.temp_dir)
        window.showFullScreen()

        window.close_current()

        self.assertFalse(window.isFullScreen())
        self.assertFalse(window.isMaximized())
        self.assertEqual(
            window.size(), QSize(MainWindow.DEFAULT_WIDTH, MainWindow.DEFAULT_HEIGHT)
        )
        self.assertTrue(window.menuBar().isVisible())
        window.deleteLater()

    def test_welcome_screen_fixed_size_and_resize_on_load(self):
        """Welcome screen is fixed size, and loading document resizes and unlocks size."""
        window = MainWindow()
        # Initial welcome screen is fixed size
        self.assertEqual(window.width(), MainWindow.DEFAULT_WIDTH)
        self.assertEqual(window.height(), MainWindow.DEFAULT_HEIGHT)
        self.assertEqual(window.minimumSize(), QSize(MainWindow.DEFAULT_WIDTH, MainWindow.DEFAULT_HEIGHT))
        self.assertEqual(window.maximumSize(), QSize(MainWindow.DEFAULT_WIDTH, MainWindow.DEFAULT_HEIGHT))

        # Open folder -> size unlocks and resizes to VIEWER_WIDTH, VIEWER_HEIGHT
        window.load_image(self.temp_dir)
        self.assertEqual(window.width(), MainWindow.VIEWER_WIDTH)
        self.assertEqual(window.height(), MainWindow.VIEWER_HEIGHT)
        self.assertEqual(window.minimumSize(), QSize(320, 180))

        # Close current -> returns to fixed welcome size
        window.close_current()
        self.assertEqual(window.width(), MainWindow.DEFAULT_WIDTH)
        self.assertEqual(window.height(), MainWindow.DEFAULT_HEIGHT)
        self.assertEqual(window.minimumSize(), QSize(MainWindow.DEFAULT_WIDTH, MainWindow.DEFAULT_HEIGHT))
        self.assertEqual(window.maximumSize(), QSize(MainWindow.DEFAULT_WIDTH, MainWindow.DEFAULT_HEIGHT))
        window.deleteLater()

    def test_escape_key_closes_window(self):
        """Pressing Escape key interrupts and closes the application."""
        window = MainWindow()
        esc_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        window.keyPressEvent(esc_event)
        self.assertTrue(window.isHidden())
        window.deleteLater()
