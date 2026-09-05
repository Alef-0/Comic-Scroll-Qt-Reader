"""Image Viewer widget and main window implementation using Qt6."""

import os
import re
import sys
from typing import List, Optional

from enum import Enum
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtCore import QEvent, Qt, QRect, QPointF, QSize, QTimer, pyqtSignal

# Import controls handlers, scroll reader, and single viewer
try:
    from src.controls.events import (
        CommonViewerControls,
        KeyboardEventHandler,
        MouseEventHandler,
    )
    from src.about_dialog import AboutDialog
    from src.hud_overlay import ViewerHud
    from src.image_pipeline import DecodeResult, ImagePipeline
    from src.pdf_handler import (
        build_pdf_page_uri,
        close_pdf_handler,
        get_pdf_handler,
        is_pdf_file,
        parse_pdf_page_uri,
    )
    from src.scroll_reader import ScrollReaderWidget
    from src.single_viewer import ImageViewerWidget, ScaledImageLabel
    from src.welcome_widget import WelcomeWidget
except ImportError:
    from controls.events import (
        CommonViewerControls,
        KeyboardEventHandler,
        MouseEventHandler,
    )
    from about_dialog import AboutDialog
    from hud_overlay import ViewerHud
    from image_pipeline import DecodeResult, ImagePipeline
    from pdf_handler import (
        build_pdf_page_uri,
        close_pdf_handler,
        get_pdf_handler,
        is_pdf_file,
        parse_pdf_page_uri,
    )
    from scroll_reader import ScrollReaderWidget
    from single_viewer import ImageViewerWidget, ScaledImageLabel
    from welcome_widget import WelcomeWidget



class ViewerMode(Enum):
    SINGLE = "single"
    SCROLL = "scroll"

SUPPORTED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
    ".gif",
    ".tif",
    ".tiff",
    ".jfif",
    ".ico",
    ".svg",
    ".tga",
}


def natural_sort_key(file_path: str) -> list:
    """Sort strings containing numbers in human/natural alphabetical order."""
    filename = os.path.basename(file_path)
    return [
        int(token) if token.isdigit() else token.casefold()
        for token in re.split(r"(\d+)", filename)
    ]



__all__ = [
    "ImageViewerWidget",
    "ScaledImageLabel",
    "ScrollReaderWidget",
    "MainWindow",
    "ViewerMode",
    "SUPPORTED_EXTENSIONS",
    "natural_sort_key",
    "WelcomeWidget",
    "ViewerHud",
]


class MainWindow(QMainWindow):
    """Main window with default 1280x720 dimensions, resizable, supporting folder discovery,
    alphabetical navigation, and zoom/pan controls.
    """

    DEFAULT_WIDTH = 580
    DEFAULT_HEIGHT = 420
    VIEWER_WIDTH = 1280
    VIEWER_HEIGHT = 720
    image_loaded = pyqtSignal(str)
    image_load_failed = pyqtSignal(str)

    def __init__(
        self,
        image_path: Optional[str] = None,
        parent=None,
        target_path: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Qt Scroll Reader - Image Viewer")

        # Image pipeline shared across both viewer widgets
        self._image_pipeline = ImagePipeline(self)
        self._image_pipeline.image_ready.connect(self._on_image_ready)
        self._image_pipeline.image_failed.connect(self._on_image_failed)

        # Mode 1: Single image viewer
        self.image_viewer = ImageViewerWidget(self)
        self.viewer = self.image_viewer
        self.image_label = self.image_viewer  # Backwards compatibility alias

        # Mode 2: Continuous scroll reader
        self.scroll_reader = ScrollReaderWidget(self, pipeline=self._image_pipeline)

        # Mode 3 / Empty state: Welcome drop-zone widget
        self.welcome_widget = WelcomeWidget(self)
        self.welcome_widget.open_file_requested.connect(self.open_file_dialog)
        self.welcome_widget.open_folder_requested.connect(self.open_folder_dialog)
        self.welcome_widget.about_requested.connect(self.show_about_dialog)

        # Central widget stack supporting both modes and welcome state
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self.image_viewer)
        self._stack.addWidget(self.scroll_reader)
        self._stack.addWidget(self.welcome_widget)
        self.setCentralWidget(self._stack)

        # Initial mode: Scroll reader mode
        self.viewer_mode = ViewerMode.SCROLL
        self._stack.setCurrentWidget(self.welcome_widget)

        # Connect image viewer signals
        self.image_viewer.next_image_requested.connect(self.next_image)
        self.image_viewer.prev_image_requested.connect(self.prev_image)
        self.image_viewer.zoom_changed.connect(lambda _: self.update_title())
        self.image_viewer.preview_size_requested.connect(
            self._request_refined_preview
        )
        self.image_viewer.full_resolution_requested.connect(
            self._request_full_resolution
        )
        self.image_viewer.toggle_mode_requested.connect(self.toggle_mode)

        # Connect scroll reader signals
        self.scroll_reader.visible_image_changed.connect(self._on_scroll_visible_changed)
        self.scroll_reader.zoom_changed.connect(lambda _: self.update_title())
        self.scroll_reader.toggle_mode_requested.connect(self.toggle_mode)
        self.scroll_reader.mode_single_requested.connect(lambda: self.set_mode(ViewerMode.SINGLE))
        self.scroll_reader.mode_scroll_requested.connect(lambda: self.set_mode(ViewerMode.SCROLL))

        # Floating bottom HUD overlay
        self._hud = ViewerHud(self)
        self._hud.first_clicked.connect(self.first_image)
        self._hud.prev_clicked.connect(self.prev_image)
        self._hud.next_clicked.connect(self.next_image)
        self._hud.last_clicked.connect(self.last_image)
        self._hud.jump_clicked.connect(self.goto_page_dialog)
        self._hud.mode_toggled.connect(self.toggle_mode)
        self._hud.zoom_in_clicked.connect(self._zoom_in)
        self._hud.zoom_out_clicked.connect(self._zoom_out)
        self._hud.zoom_reset_clicked.connect(self._reset_zoom)
        self._hud.fullscreen_toggled.connect(self.toggle_fullscreen)
        self._hud.hide()

        # Keyboard event handler
        self._keyboard_handler = KeyboardEventHandler(
            on_next_image=self.next_image,
            on_prev_image=self.prev_image,
            on_first_image=self.first_image,
            on_last_image=self.last_image,
            on_zoom_in=self._zoom_in,
            on_zoom_out=self._zoom_out,
            on_reset_zoom=self._reset_zoom,
            on_mode_single=lambda: self.set_mode(ViewerMode.SINGLE),
            on_mode_scroll=lambda: self.set_mode(ViewerMode.SCROLL),
            on_toggle_mode=self.toggle_mode,
            on_fullscreen=self.toggle_fullscreen,
            on_exit_fullscreen=self._exit_fullscreen_if_active,
            on_exit=self.close,
            on_open_file=self.open_file_dialog,
            on_open_folder=self.open_folder_dialog,
            on_close_document=self.close_current,
            on_goto_page=self.goto_page_dialog,
            on_help=self.show_shortcuts_dialog,
            on_toggle_hud=self._hud.toggle_pin,
        )

        # Enable drag-and-drop
        self.setAcceptDrops(True)
        self._stack.setAcceptDrops(True)
        self.welcome_widget.setAcceptDrops(True)
        self.image_viewer.setAcceptDrops(True)
        self.scroll_reader.setAcceptDrops(True)
        self.scroll_reader.viewport().setAcceptDrops(True)

        for widget in (
            self._stack,
            self.welcome_widget,
            self.image_viewer,
            self.scroll_reader,
            self.scroll_reader.viewport(),
        ):
            widget.installEventFilter(self)
            widget.setMouseTracking(True)
        self.setMouseTracking(True)

        # Native Menu Bar
        self._init_menu_bar()

        # Image folder discovery / PDF state
        self.folder_path: Optional[str] = None
        self.pdf_path: Optional[str] = None
        self.image_list: List[str] = []
        self.current_index: int = -1
        self._requested_index: Optional[int] = None
        self._request_generation = 0
        self._full_request_pending = False
        self._refine_request_key: Optional[tuple[str, int, int]] = None
        self._error_dialog: Optional[QMessageBox] = None

        initial_path = target_path or image_path
        if initial_path:
            self.load_image(initial_path)
        else:
            self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            self._stack.setCurrentWidget(self.welcome_widget)
            self.update_title()

    def set_mode(self, mode: ViewerMode) -> None:
        """Switch between Single Image mode and Scroll Reader mode, synchronizing current image."""
        if self.viewer_mode == mode:
            return

        self.viewer_mode = mode
        if mode == ViewerMode.SINGLE:
            # Sync active index from scroll reader to single image viewer
            idx = self.scroll_reader.current_visible_index()
            self.scroll_reader.release_render_cache()
            if 0 <= idx < len(self.image_list):
                self.current_index = idx
                self._request_index(idx, force=True)
            self._stack.setCurrentWidget(self.image_viewer)
            self.image_viewer.setFocus()
        elif mode == ViewerMode.SCROLL:
            # Sync active index from single image viewer to scroll reader
            self._request_generation += 1
            self._requested_index = None
            self._full_request_pending = False
            self._refine_request_key = None
            self._image_pipeline.cancel_queued(
                {
                    "current-preview",
                    "refined-preview",
                    "current-full",
                    "prefetch-preview",
                }
            )
            self.image_viewer.release_render_cache()
            self._stack.setCurrentWidget(self.scroll_reader)
            self.scroll_reader.setFocus()
            if 0 <= self.current_index < len(self.image_list):
                self.scroll_reader.scroll_to_index(self.current_index)

        self.update_title()

    def toggle_mode(self) -> None:
        """Alternate between Single Image and Scroll Reader modes."""
        if self.viewer_mode == ViewerMode.SCROLL:
            self.set_mode(ViewerMode.SINGLE)
        else:
            self.set_mode(ViewerMode.SCROLL)

    def _on_scroll_visible_changed(self, index: int) -> None:
        """Update current index and title when scrolling in Scroll Reader mode."""
        if self.viewer_mode == ViewerMode.SCROLL and 0 <= index < len(self.image_list):
            self.current_index = index
            self.update_title()

    def _zoom_in(self) -> None:
        self.image_viewer.zoom_in()
        self.scroll_reader.zoom_in()

    def _zoom_out(self) -> None:
        self.image_viewer.zoom_out()
        self.scroll_reader.zoom_out()

    def _reset_zoom(self) -> None:
        self.image_viewer.reset_view()
        self.scroll_reader.reset_zoom()

    def discover_images(
        self, folder_path: str, initial_file: Optional[str] = None
    ) -> bool:
        """Scan a folder for supported images, sort them alphabetically, and open the target."""
        if self.pdf_path:
            close_pdf_handler(self.pdf_path)
            self.pdf_path = None

        self.folder_path = os.path.abspath(folder_path)
        discovered = []

        if os.path.exists(self.folder_path) and os.path.isdir(self.folder_path):
            try:
                for entry in os.scandir(self.folder_path):
                    if entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in SUPPORTED_EXTENSIONS:
                            discovered.append(entry.path)
            except OSError as e:
                print(f"Error reading folder '{self.folder_path}': {e}", file=sys.stderr)

        self.image_list = sorted(discovered, key=natural_sort_key)

        requested_index = 0 if self.image_list else -1
        if initial_file:
            init_abs = os.path.abspath(initial_file)
            init_ext = os.path.splitext(init_abs)[1].lower()
            if (
                init_abs not in self.image_list
                and os.path.isfile(init_abs)
                and init_ext in SUPPORTED_EXTENSIONS
            ):
                self.image_list.append(init_abs)
                self.image_list.sort(key=natural_sort_key)

            try:
                requested_index = self.image_list.index(init_abs)
            except ValueError:
                requested_index = 0 if self.image_list else -1

        self.current_index = -1
        self._requested_index = None

        if self.image_list and requested_index >= 0:
            self.setMinimumSize(320, 180)
            self.setMaximumSize(16777215, 16777215)
            self.resize(self.VIEWER_WIDTH, self.VIEWER_HEIGHT)
            target_widget = (
                self.scroll_reader
                if self.viewer_mode == ViewerMode.SCROLL
                else self.image_viewer
            )
            self._stack.setCurrentWidget(target_widget)
            self.scroll_reader.set_images(self.image_list, start_index=requested_index)
            res = self._request_index(requested_index, force=True)
            self._hud.set_page_info(requested_index, len(self.image_list))
            self._hud.set_mode(self.viewer_mode == ViewerMode.SCROLL)
            self._hud.reposition(self.width(), self.height())
            self._hud.on_user_interaction()
            return res
        else:
            self.image_viewer.clear()
            self.scroll_reader.clear()
            self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            self._stack.setCurrentWidget(self.welcome_widget)
            self._hud.hide()
            self.update_title()
            return False

    def open_pdf(self, pdf_path: str, start_page: int = 0) -> bool:
        """Open a PDF document, acquire all page URIs and sizes, and display in scroll mode by default."""
        resolved = os.path.abspath(pdf_path)
        if not is_pdf_file(resolved):
            return False

        if self.pdf_path and self.pdf_path != resolved:
            close_pdf_handler(self.pdf_path)

        try:
            handler = get_pdf_handler(resolved)
        except Exception as e:
            self._show_load_error(resolved, f"Could not open PDF:\n{e}")
            return False

        if handler.page_count <= 0:
            self.image_viewer.clear()
            self.scroll_reader.clear()
            self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            self._stack.setCurrentWidget(self.welcome_widget)
            self._hud.hide()
            self.update_title()
            return False

        self.pdf_path = resolved
        self.folder_path = os.path.dirname(resolved)
        self.image_list = [
            build_pdf_page_uri(resolved, i) for i in range(handler.page_count)
        ]

        # Unlock sizing for reading view
        self.setMinimumSize(320, 180)
        self.setMaximumSize(16777215, 16777215)
        self.resize(self.VIEWER_WIDTH, self.VIEWER_HEIGHT)

        # PDF documents open by default on scroll mode
        self.viewer_mode = ViewerMode.SCROLL
        self._stack.setCurrentWidget(self.scroll_reader)

        requested_index = max(0, min(start_page, len(self.image_list) - 1))
        self.current_index = -1
        self._requested_index = None

        self.scroll_reader.set_images(self.image_list, start_index=requested_index)
        res = self._request_index(requested_index, force=True)
        self._hud.set_page_info(requested_index, len(self.image_list))
        self._hud.set_mode(True)
        self._hud.reposition(self.width(), self.height())
        self._hud.on_user_interaction()
        return res

    def load_image(self, image_path: str) -> bool:
        """Load an image file, PDF document, or discover folder images."""
        resolved = os.path.abspath(image_path)
        if is_pdf_file(resolved):
            return self.open_pdf(resolved)
        if os.path.isdir(resolved):
            return self.discover_images(resolved)
        return self.discover_images(os.path.dirname(resolved), initial_file=resolved)

    def open_path(self, target_path: str) -> bool:
        """Open an image file, PDF file, or directory."""
        return self.load_image(target_path)

    def load_current_image(self) -> bool:
        """Asynchronously reload the selected or currently displayed image."""
        index = (
            self._requested_index
            if self._requested_index is not None
            else self.current_index
        )
        if not self.image_list or not (0 <= index < len(self.image_list)):
            self.image_viewer.clear()
            self.scroll_reader.clear()
            self.update_title()
            return False
        return self._request_index(index, force=True)

    def _display_name(self, path: str) -> str:
        """Format filename for title display, distinguishing PDF pages."""
        pdf_info = parse_pdf_page_uri(path)
        if pdf_info is not None:
            pdf_file, page_idx = pdf_info
            return f"{os.path.basename(pdf_file)} (Page {page_idx + 1})"
        return os.path.basename(path)

    def update_title(self):
        """Update window title with [X/Total] counter, filename, dimensions, and zoom."""
        if not self.image_list:
            self.setWindowTitle("Qt Scroll Reader - [0/0] No images found")
            if hasattr(self, "_hud"):
                self._hud.hide()
            return

        mode_tag = " [Scroll]" if self.viewer_mode == ViewerMode.SCROLL else ""

        if self._requested_index is not None:
            path = self.image_list[self._requested_index]
            filename = self._display_name(path)
            self.setWindowTitle(
                f"Qt Scroll Reader{mode_tag} - [{self._requested_index + 1}/{len(self.image_list)}] "
                f"Loading {filename}…"
            )
            if hasattr(self, "_hud"):
                self._hud.set_page_info(self._requested_index, len(self.image_list))
            return

        if not (0 <= self.current_index < len(self.image_list)):
            self.setWindowTitle("Qt Scroll Reader - [0/0] No image displayed")
            if hasattr(self, "_hud"):
                self._hud.hide()
            return

        path = self.image_list[self.current_index]
        filename = self._display_name(path)
        source_size = (
            self.scroll_reader._get_source_size(path)
            if self.viewer_mode == ViewerMode.SCROLL
            else self.image_viewer.source_size
        )
        dim_str = (
            f" ({source_size.width()}x{source_size.height()})"
            if source_size.isValid()
            else ""
        )

        if self.viewer_mode == ViewerMode.SCROLL:
            mode_tag = " [Scroll]"
            zoom_factor = self.scroll_reader.zoom_factor
        else:
            mode_tag = ""
            zoom_factor = self.image_viewer.zoom_factor

        zoom_pct = int(round(zoom_factor * 100))
        zoom_str = f" - {zoom_pct}%" if zoom_pct != 100 else ""

        self.setWindowTitle(
            f"Qt Scroll Reader{mode_tag} - [{self.current_index + 1}/{len(self.image_list)}] {filename}{dim_str}{zoom_str}"
        )
        if hasattr(self, "_hud"):
            self._hud.set_page_info(self.current_index, len(self.image_list))
            self._hud.set_mode(self.viewer_mode == ViewerMode.SCROLL)
            self._hud.set_zoom(zoom_factor)

    def next_image(self):
        """Navigate to next image in alphabetical order."""
        base_index = self._effective_index()
        if self.image_list and base_index < len(self.image_list) - 1:
            self.go_to_index(base_index + 1)

    def prev_image(self):
        """Navigate to previous image in alphabetical order."""
        base_index = self._effective_index()
        if self.image_list and base_index > 0:
            self.go_to_index(base_index - 1)

    def first_image(self):
        """Navigate to the first image."""
        if self.image_list:
            self.go_to_index(0)

    def last_image(self):
        """Navigate to the last image."""
        if self.image_list:
            self.go_to_index(len(self.image_list) - 1)

    def go_to_index(self, index: int):
        """Request an image and commit the index only after decoding succeeds."""
        if 0 <= index < len(self.image_list) and index != self._effective_index():
            self._request_index(index)

    def _effective_index(self) -> int:
        if self._requested_index is not None:
            return self._requested_index
        return self.current_index

    def _request_index(self, index: int, force: bool = False) -> bool:
        if not (0 <= index < len(self.image_list)):
            return False
        if not force and index == self._effective_index():
            return False

        self._request_generation += 1
        self._requested_index = index
        self._full_request_pending = False
        self._refine_request_key = None
        self._image_pipeline.cancel_queued(
            {
                "current-preview",
                "refined-preview",
                "current-full",
                "prefetch-preview",
            }
        )
        self.image_viewer.release_full_resolution()
        self.update_title()
        self._image_pipeline.request_preview(
            self.image_list[index],
            self.image_viewer.preview_bounds(),
            self._request_generation,
            purpose="current-preview",
            priority=2,
        )
        return True

    def _on_image_ready(self, result: DecodeResult) -> None:
        request = result.request
        if request.purpose == "prefetch-preview":
            return
        if request.request_id != self._request_generation:
            return

        if request.purpose == "current-preview":
            if self._requested_index is None:
                return
            expected_path = self.image_list[self._requested_index]
            if request.path != expected_path:
                return

            accepted_index = self._requested_index
            self.current_index = accepted_index
            self._requested_index = None
            if self.viewer_mode == ViewerMode.SCROLL:
                self.scroll_reader.scroll_to_index(accepted_index)
            pixmap = QPixmap.fromImage(result.image)
            self.image_viewer.set_preview_pixmap(
                pixmap, result.source_size, request.path, reset_view=True
            )
            self.update_title()
            self.image_loaded.emit(request.path)
            self._prefetch_neighbours()
            return

        if not (0 <= self.current_index < len(self.image_list)):
            return
        current_path = self.image_list[self.current_index]
        if request.path != current_path:
            return

        pixmap = QPixmap.fromImage(result.image)
        if request.purpose == "refined-preview":
            self._refine_request_key = None
            self.image_viewer.set_refined_preview_pixmap(pixmap, current_path)
        elif request.purpose == "current-full":
            self._full_request_pending = False
            if self.image_viewer.zoom_factor > 1.0:
                self.image_viewer.set_full_resolution_pixmap(pixmap, current_path)

    def _on_image_failed(self, result: DecodeResult) -> None:
        request = result.request
        if request.request_id != self._request_generation:
            return
        if request.purpose == "refined-preview":
            self._refine_request_key = None
            return
        if request.purpose == "current-full":
            self._full_request_pending = False
            return
        if request.purpose != "current-preview" or self._requested_index is None:
            return

        failed_path = request.path
        self._requested_index = None
        if self.current_index < 0:
            self.image_viewer.clear()
        self.update_title()
        self.image_load_failed.emit(failed_path)
        self._show_load_error(failed_path, result.error)

    def _request_refined_preview(self, bounds: QSize) -> None:
        if not (0 <= self.current_index < len(self.image_list)):
            return
        path = self.image_list[self.current_index]
        key = (path, bounds.width(), bounds.height())
        if key == self._refine_request_key:
            return
        self._refine_request_key = key
        self._image_pipeline.request_preview(
            path,
            bounds,
            self._request_generation,
            purpose="refined-preview",
            priority=1,
        )

    def _request_full_resolution(self) -> None:
        if self._full_request_pending:
            return
        if not (0 <= self.current_index < len(self.image_list)):
            return
        bounds = self.image_viewer.detail_bounds()
        if not bounds.isValid():
            return
        self._full_request_pending = True
        self._image_pipeline.request_preview(
            self.image_list[self.current_index],
            bounds,
            self._request_generation,
            purpose="current-full",
            priority=1,
        )

    def _prefetch_neighbours(self) -> None:
        if not (0 <= self.current_index < len(self.image_list)):
            return
        neighbour_indices = {
            index
            for index in (
                self.current_index - 1,
                self.current_index,
                self.current_index + 1,
            )
            if 0 <= index < len(self.image_list)
        }
        retained_paths = {self.image_list[index] for index in neighbour_indices}
        self._image_pipeline.retain_preview_paths(retained_paths)
        bounds = self.image_viewer.preview_bounds()
        for index in sorted(neighbour_indices - {self.current_index}):
            self._image_pipeline.request_preview(
                self.image_list[index],
                bounds,
                self._request_generation,
                purpose="prefetch-preview",
                priority=0,
            )

    def _show_load_error(self, path: str, detail: str) -> None:
        if self._error_dialog is not None:
            self._error_dialog.close()
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("Error Loading Image")
        dialog.setText(f"Could not load image:\n{path}")
        if detail:
            dialog.setInformativeText(detail)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.finished.connect(
            lambda _result, dialog=dialog: self._clear_error_dialog(dialog)
        )
        self._error_dialog = dialog
        dialog.open()

    def _clear_error_dialog(self, dialog: QMessageBox) -> None:
        if self._error_dialog is dialog:
            self._error_dialog = None

    def _init_menu_bar(self):
        menubar = self.menuBar()
        menubar.setStyleSheet(
            "QMenuBar { background-color: #222222; color: #e0e0e0; font-size: 13px; }"
            "QMenuBar::item { background: transparent; padding: 4px 10px; }"
            "QMenuBar::item:selected { background-color: #383838; color: #ffffff; }"
            "QMenu { background-color: #2b2b2b; color: #e0e0e0; border: 1px solid #444; }"
            "QMenu::item { padding: 6px 24px 6px 20px; }"
            "QMenu::item:selected { background-color: #4a90e2; color: #ffffff; }"
            "QMenu::separator { height: 1px; background-color: #3d3d3d; margin: 4px 0px; }"
        )

        # File Menu
        file_menu = menubar.addMenu("&File")

        open_file_action = QAction("&Open File...", self)
        open_file_action.setShortcut("Ctrl+O")
        open_file_action.triggered.connect(self.open_file_dialog)
        file_menu.addAction(open_file_action)

        open_folder_action = QAction("Open &Folder...", self)
        open_folder_action.setShortcut("Ctrl+Shift+O")
        open_folder_action.triggered.connect(self.open_folder_dialog)
        file_menu.addAction(open_folder_action)

        close_action = QAction("&Close Document", self)
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(self.close_current)
        file_menu.addAction(close_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View Menu
        view_menu = menubar.addMenu("&View")

        mode_scroll_action = QAction("Continuous &Scroll Mode", self)
        mode_scroll_action.setShortcut("2")
        mode_scroll_action.triggered.connect(lambda: self.set_mode(ViewerMode.SCROLL))
        view_menu.addAction(mode_scroll_action)

        mode_single_action = QAction("Single &Page Mode", self)
        mode_single_action.setShortcut("1")
        mode_single_action.triggered.connect(lambda: self.set_mode(ViewerMode.SINGLE))
        view_menu.addAction(mode_single_action)

        view_menu.addSeparator()

        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut("Ctrl++")
        zoom_in_action.triggered.connect(self._zoom_in)
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut("Ctrl+-")
        zoom_out_action.triggered.connect(self._zoom_out)
        view_menu.addAction(zoom_out_action)

        zoom_reset_action = QAction("&Fit / Reset Zoom", self)
        zoom_reset_action.setShortcut("Ctrl+0")
        zoom_reset_action.triggered.connect(self._reset_zoom)
        view_menu.addAction(zoom_reset_action)

        view_menu.addSeparator()

        fs_action = QAction("Toggle &Fullscreen", self)
        fs_action.setShortcut("F11")
        fs_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fs_action)

        hud_action = QAction("Toggle &HUD", self)
        hud_action.setShortcut("H")
        hud_action.triggered.connect(self._hud.toggle_pin)
        view_menu.addAction(hud_action)

        # Navigate Menu
        nav_menu = menubar.addMenu("&Navigate")

        next_action = QAction("&Next Page", self)
        next_action.setShortcut("Right")
        next_action.triggered.connect(self.next_image)
        nav_menu.addAction(next_action)

        prev_action = QAction("&Previous Page", self)
        prev_action.setShortcut("Left")
        prev_action.triggered.connect(self.prev_image)
        nav_menu.addAction(prev_action)

        first_action = QAction("&First Page", self)
        first_action.setShortcut("Home")
        first_action.triggered.connect(self.first_image)
        nav_menu.addAction(first_action)

        last_action = QAction("&Last Page", self)
        last_action.setShortcut("End")
        last_action.triggered.connect(self.last_image)
        nav_menu.addAction(last_action)

        nav_menu.addSeparator()

        goto_action = QAction("&Go to Page...", self)
        goto_action.setShortcut("Ctrl+G")
        goto_action.triggered.connect(self.goto_page_dialog)
        nav_menu.addAction(goto_action)

        # Help Menu
        help_menu = menubar.addMenu("&Help")

        shortcuts_action = QAction("Keyboard &Shortcuts", self)
        shortcuts_action.setShortcut("F1")
        shortcuts_action.triggered.connect(self.show_shortcuts_dialog)
        help_menu.addAction(shortcuts_action)

        about_action = QAction("&About Qt Scroll Reader", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def _can_accept_drag(self, event) -> bool:
        mime = event.mimeData()
        if not mime or not mime.hasUrls():
            return False
        for url in mime.urls():
            if url.isLocalFile():
                if self._is_supported_drag_path(url.toLocalFile()):
                    return True
        return False

    def _extract_valid_drag_path(self, event) -> Optional[str]:
        mime = event.mimeData()
        if not mime or not mime.hasUrls():
            return None
        for url in mime.urls():
            if url.isLocalFile():
                local_path = url.toLocalFile()
                if self._is_supported_drag_path(local_path):
                    return local_path
        return None

    def _is_supported_drag_path(self, path: str) -> bool:
        if not path or not os.path.exists(path):
            return False
        if os.path.isdir(path):
            return True
        if is_pdf_file(path):
            return True
        ext = os.path.splitext(path)[1].lower()
        return ext in SUPPORTED_EXTENSIONS

    def _set_drag_visual_hover(self, hover: bool):
        if hasattr(self, "welcome_widget"):
            self.welcome_widget.set_drag_hover(hover)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._can_accept_drag(event):
            event.acceptProposedAction()
            self._set_drag_visual_hover(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if self._can_accept_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._set_drag_visual_hover(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self._set_drag_visual_hover(False)
        path = self._extract_valid_drag_path(event)
        if path:
            event.acceptProposedAction()
            self.load_image(path)
        else:
            event.ignore()

    def eventFilter(self, watched, event: QEvent) -> bool:
        etype = event.type()
        if etype == QEvent.Type.DragEnter:
            if self._can_accept_drag(event):
                event.acceptProposedAction()
                self._set_drag_visual_hover(True)
                return True
            else:
                event.ignore()
                return True
        elif etype == QEvent.Type.DragMove:
            if self._can_accept_drag(event):
                event.acceptProposedAction()
                return True
            else:
                event.ignore()
                return True
        elif etype == QEvent.Type.DragLeave:
            self._set_drag_visual_hover(False)
            return True
        elif etype == QEvent.Type.Drop:
            self._set_drag_visual_hover(False)
            path = self._extract_valid_drag_path(event)
            if path:
                event.acceptProposedAction()
                self.load_image(path)
                return True
            else:
                event.ignore()
                return True
        elif etype == QEvent.Type.MouseMove:
            if self.image_list:
                self._hud.on_user_interaction()
        return super().eventFilter(watched, event)

    def open_file_dialog(self):
        """Show open file dialog for images and PDF files."""
        filter_exts = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
        file_filter = (
            f"Supported Files (*.pdf {filter_exts});;"
            f"PDF Documents (*.pdf);;"
            f"Images ({filter_exts});;"
            f"All Files (*)"
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image or PDF Document",
            self.folder_path or "",
            file_filter,
        )
        if path:
            self.load_image(path)

    def open_folder_dialog(self):
        """Show open directory dialog to read a comic folder."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Open Comic Folder",
            self.folder_path or "",
        )
        if dir_path:
            self.discover_images(dir_path)

    def goto_page_dialog(self):
        """Prompt user for a page number to jump to."""
        if not self.image_list:
            return
        total = len(self.image_list)
        current = self.current_index + 1 if self.current_index >= 0 else 1
        page, ok = QInputDialog.getInt(
            self,
            "Go to Page",
            f"Enter page number (1 - {total}):",
            value=current,
            min=1,
            max=total,
        )
        if ok:
            target_idx = page - 1
            if self.viewer_mode == ViewerMode.SCROLL:
                self.scroll_reader.scroll_to_index(target_idx)
                self.current_index = target_idx
                self.update_title()
                self._hud.set_page_info(target_idx, total)
            else:
                self.go_to_index(target_idx)

    def show_shortcuts_dialog(self):
        """Display keyboard and mouse shortcuts reference."""
        html = """
        <h3>Keyboard & Mouse Shortcuts</h3>
        <table border="0" cellpadding="4" cellspacing="2" style="color: #eee;">
          <tr><td><b>1 / 2</b></td><td>Switch to Single / Continuous Scroll mode</td></tr>
          <tr><td><b>F11 or F</b></td><td>Toggle Fullscreen</td></tr>
          <tr><td><b>Esc</b></td><td>Exit Fullscreen</td></tr>
          <tr><td><b>Ctrl+O</b></td><td>Open Image or PDF File</td></tr>
          <tr><td><b>Ctrl+Shift+O</b></td><td>Open Comic Folder</td></tr>
          <tr><td><b>Ctrl+W</b></td><td>Close Current Document</td></tr>
          <tr><td><b>Ctrl+G</b></td><td>Go to Page...</td></tr>
          <tr><td><b>H</b></td><td>Toggle Bottom HUD Overlay</td></tr>
          <tr><td><b>Right / Down / Space / PageDown</b></td><td>Next Page</td></tr>
          <tr><td><b>Left / Up / PageUp / Backspace</b></td><td>Previous Page</td></tr>
          <tr><td><b>Home / End</b></td><td>First / Last Page</td></tr>
          <tr><td><b>Ctrl + Plus / Minus</b></td><td>Zoom In / Out</td></tr>
          <tr><td><b>Ctrl + 0</b></td><td>Reset Zoom to Fit</td></tr>
          <tr><td><b>Ctrl + Mouse Wheel</b></td><td>Anchored Zoom In / Out</td></tr>
          <tr><td><b>Esc</b></td><td>Close Application (Interrupt)</td></tr>
          <tr><td><b>Ctrl+C</b></td><td>Terminal Interrupt (Close Application)</td></tr>
          <tr><td><b>Left Click + Drag</b></td><td>Pan Image / Viewport</td></tr>
          <tr><td><b>Double Click</b></td><td>Reset Zoom / View</td></tr>
          <tr><td><b>Right Click</b></td><td>Toggle View Mode</td></tr>
          <tr><td><b>Middle Click</b></td><td>Next Page</td></tr>
        </table>
        """
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Shortcuts - Qt Scroll Reader")
        dialog.setTextFormat(Qt.TextFormat.RichText)
        dialog.setText(html)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.exec()

    def show_about_dialog(self):
        """Display the custom project and technology overview."""
        dialog = AboutDialog(self)
        dialog.exec()

    def close_current(self):
        """Close current document or folder and return to welcome screen."""
        if self.pdf_path:
            close_pdf_handler(self.pdf_path)
            self.pdf_path = None
        self.folder_path = None
        self.image_list = []
        self.current_index = -1
        self._requested_index = None
        self.image_viewer.clear()
        self.scroll_reader.clear()
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self._stack.setCurrentWidget(self.welcome_widget)
        self._hud.hide()
        self.update_title()

    def toggle_fullscreen(self):
        """Toggle fullscreen mode on and off."""
        if self.isFullScreen():
            self.showNormal()
            self.menuBar().setVisible(True)
            self._hud.set_fullscreen(False)
        else:
            self.showFullScreen()
            self.menuBar().setVisible(False)
            self._hud.set_fullscreen(True)
        self._hud.reposition(self.width(), self.height())
        if self.image_list:
            self._hud.on_user_interaction()

    def _exit_fullscreen_if_active(self):
        if self.isFullScreen():
            self.toggle_fullscreen()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._hud.reposition(self.width(), self.height())

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard navigation and shortcuts."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if not self._keyboard_handler.handle_key_press(event):
            if self.viewer_mode == ViewerMode.SCROLL and self.image_list:
                self.scroll_reader.keyPressEvent(event)
            else:
                super().keyPressEvent(event)

    def closeEvent(self, event):
        """Clean up resources on window close."""
        if self.pdf_path:
            close_pdf_handler(self.pdf_path)
            self.pdf_path = None
        super().closeEvent(event)
