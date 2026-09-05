"""Image Viewer widget and main window implementation using Qt6."""

import os
import re
import sys
from typing import List, Optional

from enum import Enum
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QMessageBox, QStackedWidget
from PyQt6.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtCore import Qt, QRect, QPointF, QSize, QTimer, pyqtSignal

# Import controls handlers, scroll reader, and single viewer
try:
    from src.controls.events import (
        CommonViewerControls,
        KeyboardEventHandler,
        MouseEventHandler,
    )
    from src.image_pipeline import DecodeResult, ImagePipeline
    from src.scroll_reader import ScrollReaderWidget
    from src.single_viewer import ImageViewerWidget, ScaledImageLabel
except ImportError:
    from controls.events import (
        CommonViewerControls,
        KeyboardEventHandler,
        MouseEventHandler,
    )
    from image_pipeline import DecodeResult, ImagePipeline
    from scroll_reader import ScrollReaderWidget
    from single_viewer import ImageViewerWidget, ScaledImageLabel



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
]


class MainWindow(QMainWindow):
    """Main window with default 1280x720 dimensions, resizable, supporting folder discovery,
    alphabetical navigation, and zoom/pan controls.
    """

    DEFAULT_WIDTH = 1280
    DEFAULT_HEIGHT = 720
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

        # Set default 1280x720 resizable window
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setMinimumSize(320, 180)

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

        # Central widget stack supporting both modes
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self.image_viewer)
        self._stack.addWidget(self.scroll_reader)
        self.setCentralWidget(self._stack)

        # Initial mode: Scroll reader mode
        self.viewer_mode = ViewerMode.SCROLL
        self._stack.setCurrentWidget(self.scroll_reader)

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
        )

        # Image folder discovery state
        self.folder_path: Optional[str] = None
        self.image_list: List[str] = []
        self.current_index: int = -1
        self._requested_index: Optional[int] = None
        self._request_generation = 0
        self._full_request_pending = False
        self._refine_request_key: Optional[tuple[str, int, int]] = None
        self._error_dialog: Optional[QMessageBox] = None

        initial_path = target_path or image_path
        if initial_path:
            resolved = os.path.abspath(initial_path)
            if os.path.isdir(resolved):
                self.discover_images(resolved)
            else:
                self.discover_images(os.path.dirname(resolved), initial_file=resolved)

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
            self.scroll_reader.set_images(self.image_list, start_index=requested_index)
            return self._request_index(requested_index, force=True)
        else:
            self.image_viewer.clear()
            self.scroll_reader.clear()
            self.update_title()
            return False

    def load_image(self, image_path: str) -> bool:
        """Load an image file and discover its folder images."""
        resolved = os.path.abspath(image_path)
        if os.path.isdir(resolved):
            return self.discover_images(resolved)
        return self.discover_images(os.path.dirname(resolved), initial_file=resolved)

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

    def update_title(self):
        """Update window title with [X/Total] counter, filename, dimensions, and zoom."""
        if not self.image_list:
            self.setWindowTitle("Qt Scroll Reader - [0/0] No images found")
            return

        mode_tag = " [Scroll]" if self.viewer_mode == ViewerMode.SCROLL else ""

        if self._requested_index is not None:
            path = self.image_list[self._requested_index]
            filename = os.path.basename(path)
            self.setWindowTitle(
                f"Qt Scroll Reader{mode_tag} - [{self._requested_index + 1}/{len(self.image_list)}] "
                f"Loading {filename}…"
            )
            return

        if not (0 <= self.current_index < len(self.image_list)):
            self.setWindowTitle("Qt Scroll Reader - [0/0] No image displayed")
            return

        path = self.image_list[self.current_index]
        filename = os.path.basename(path)
        source_size = self.image_viewer.source_size
        dim_str = (
            f" ({source_size.width()}x{source_size.height()})"
            if source_size.isValid()
            else ""
        )

        if self.viewer_mode == ViewerMode.SCROLL:
            mode_tag = " [Scroll]"
            zoom_pct = int(round(self.scroll_reader.zoom_factor * 100))
        else:
            mode_tag = ""
            zoom_pct = int(round(self.image_viewer.zoom_factor * 100))

        zoom_str = f" - {zoom_pct}%" if zoom_pct != 100 else ""

        self.setWindowTitle(
            f"Qt Scroll Reader{mode_tag} - [{self.current_index + 1}/{len(self.image_list)}] {filename}{dim_str}{zoom_str}"
        )

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

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard navigation and shortcuts."""
        if not self._keyboard_handler.handle_key_press(event):
            if self.viewer_mode == ViewerMode.SCROLL:
                self.scroll_reader.keyPressEvent(event)
            else:
                super().keyPressEvent(event)
