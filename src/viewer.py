"""Image Viewer widget and main window implementation using Qt6."""

import os
import re
import sys
from typing import List, Optional

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QMessageBox
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

# Import controls handlers
try:
    from src.controls.events import KeyboardEventHandler, MouseEventHandler
    from src.image_pipeline import DecodeResult, ImagePipeline
except ImportError:
    from controls.events import KeyboardEventHandler, MouseEventHandler
    from image_pipeline import DecodeResult, ImagePipeline

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


class ImageViewerWidget(QWidget):
    """Custom QWidget that uses QPainter to dynamically draw, scale, zoom, and pan
    its image while strictly preserving aspect ratio.
    """

    next_image_requested = pyqtSignal()
    prev_image_requested = pyqtSignal()
    zoom_changed = pyqtSignal(float)
    preview_size_requested = pyqtSignal(QSize)
    full_resolution_requested = pyqtSignal()

    MIN_ZOOM = 0.1
    MAX_ZOOM = 50.0
    QUALITY_DELAY_MS = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)  # Allows window to shrink freely without getting blocked
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._preview_pixmap: Optional[QPixmap] = None
        self._full_pixmap: Optional[QPixmap] = None
        self._source_size = QSize()
        self._image_path: Optional[str] = None
        self._zoom_factor: float = 1.0
        self._pan_offset: QPointF = QPointF(0.0, 0.0)
        self._interactive_transform = False

        self._quality_timer = QTimer(self)
        self._quality_timer.setSingleShot(True)
        self._quality_timer.setInterval(self.QUALITY_DELAY_MS)
        self._quality_timer.timeout.connect(self._finish_interaction)

        # Delegate mouse events to MouseEventHandler
        self._mouse_handler = MouseEventHandler(
            on_pan=self.pan_by,
            on_zoom_anchor=self.zoom_at,
            on_next_image=self.next_image_requested.emit,
            on_prev_image=self.prev_image_requested.emit,
            on_reset_view=self.reset_view,
            on_cursor_change=self.setCursor,
        )

    @property
    def zoom_factor(self) -> float:
        """Return the current zoom factor (1.0 = fit to window)."""
        return self._zoom_factor

    @property
    def pan_offset(self) -> QPointF:
        """Return current pan offset from center."""
        return self._pan_offset

    def set_pixmap(self, pixmap: QPixmap):
        """Set an already-loaded pixmap directly, primarily for embedded callers."""
        self._preview_pixmap = pixmap
        self._full_pixmap = pixmap
        self._source_size = pixmap.size()
        self._image_path = None
        self.reset_view()

    def pixmap(self) -> Optional[QPixmap]:
        """Return the pixels currently selected for painting."""
        return self._active_pixmap()

    @property
    def source_size(self) -> QSize:
        """Return original file dimensions, independent of preview resolution."""
        return QSize(self._source_size)

    @property
    def image_path(self) -> Optional[str]:
        return self._image_path

    def preview_bounds(self) -> QSize:
        """Return viewport dimensions in physical pixels for preview decoding."""
        dpr = self.devicePixelRatioF()
        return QSize(
            max(1, int(round(self.width() * dpr))),
            max(1, int(round(self.height() * dpr))),
        )

    def set_preview_pixmap(
        self,
        pixmap: QPixmap,
        source_size: QSize,
        image_path: str,
        reset_view: bool = True,
    ) -> None:
        """Atomically replace the display preview without retaining the old full image."""
        self._preview_pixmap = pixmap
        self._full_pixmap = None
        self._source_size = QSize(source_size)
        self._image_path = image_path
        self._interactive_transform = False
        if reset_view:
            self.reset_view()
            if not self._full_resolution_needed():
                self._quality_timer.stop()
        else:
            self.update()

    def set_refined_preview_pixmap(self, pixmap: QPixmap, image_path: str) -> None:
        """Replace only the small render surface while preserving zoom and pan."""
        if image_path != self._image_path:
            return
        self._preview_pixmap = pixmap
        if self._zoom_factor <= 1.0:
            self._full_pixmap = None
        self.update()

    def set_full_resolution_pixmap(self, pixmap: QPixmap, image_path: str) -> None:
        """Install full pixels for detailed zoom without changing view geometry."""
        if image_path != self._image_path:
            return
        self._full_pixmap = pixmap
        self.update()

    def release_full_resolution(self) -> None:
        """Drop the large buffer while retaining the small transition preview."""
        self._full_pixmap = None
        self.update()

    def clear(self):
        """Clear current image and repaint empty canvas."""
        self._preview_pixmap = None
        self._full_pixmap = None
        self._source_size = QSize()
        self._image_path = None
        self._quality_timer.stop()
        self.reset_view()

    def reset_view(self):
        """Reset zoom factor and pan offset back to centered fit-to-window."""
        self._zoom_factor = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._full_pixmap = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        self.zoom_changed.emit(self._zoom_factor)
        self._schedule_quality_update()

    def pan_by(self, delta_x: float, delta_y: float):
        """Translate the image by a given delta offset."""
        self._pan_offset += QPointF(delta_x, delta_y)
        self._begin_interaction()
        self.update()

    def zoom_at(self, scale_factor: float, anchor_pos: Optional[QPointF] = None):
        """Zoom in or out anchored around a specific widget coordinate, preserving aspect ratio."""
        if not self._has_image():
            return

        w_size = self.size()
        if w_size.width() <= 0 or w_size.height() <= 0:
            return

        base_size = self._source_size.scaled(
            w_size, Qt.AspectRatioMode.KeepAspectRatio
        )
        base_w = base_size.width()
        base_h = base_size.height()
        if base_w <= 0 or base_h <= 0:
            return

        cur_w = base_w * self._zoom_factor
        cur_h = base_h * self._zoom_factor
        cur_x = (w_size.width() - cur_w) / 2.0 + self._pan_offset.x()
        cur_y = (w_size.height() - cur_h) / 2.0 + self._pan_offset.y()

        if anchor_pos is None:
            ax = w_size.width() / 2.0
            ay = w_size.height() / 2.0
        else:
            ax = anchor_pos.x()
            ay = anchor_pos.y()

        # Normalized coordinates relative to the current image rectangle
        fx = (ax - cur_x) / cur_w
        fy = (ay - cur_y) / cur_h

        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom_factor * scale_factor))
        if abs(new_zoom - self._zoom_factor) < 1e-6:
            return

        new_w = base_w * new_zoom
        new_h = base_h * new_zoom

        # Maintain anchor point stationary
        new_x = ax - fx * new_w
        new_y = ay - fy * new_h

        new_pan_x = new_x - (w_size.width() - new_w) / 2.0
        new_pan_y = new_y - (w_size.height() - new_h) / 2.0

        self._zoom_factor = new_zoom
        self._pan_offset = QPointF(new_pan_x, new_pan_y)
        self._begin_interaction()

        # Update cursor shape when zoomed in
        if not self._mouse_handler.is_dragging:
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._zoom_factor > 1.0
                else Qt.CursorShape.ArrowCursor
            )

        self.update()
        self.zoom_changed.emit(self._zoom_factor)

    def zoom_in(self):
        """Zoom in centered on widget."""
        self.zoom_at(1.25)

    def zoom_out(self):
        """Zoom out centered on widget."""
        self.zoom_at(0.8)

    def target_rect(self) -> QRect:
        """Calculate the target rectangle of the image within widget bounds,
        accounting for zoom and pan while preserving aspect ratio.
        """
        if not self._has_image():
            return QRect()

        widget_size = self.size()
        if widget_size.width() <= 0 or widget_size.height() <= 0:
            return QRect()

        base_size = self._source_size.scaled(
            widget_size, Qt.AspectRatioMode.KeepAspectRatio
        )
        w = base_size.width() * self._zoom_factor
        h = base_size.height() * self._zoom_factor
        x = (widget_size.width() - w) / 2.0 + self._pan_offset.x()
        y = (widget_size.height() - h) / 2.0 + self._pan_offset.y()

        return QRect(int(round(x)), int(round(y)), int(round(w)), int(round(h)))

    def paintEvent(self, event):
        """Draw one complete buffered frame using the cheapest suitable pixel source."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))

        pixmap = self._active_pixmap()
        if (
            pixmap is not None
            and not pixmap.isNull()
            and self.width() > 0
            and self.height() > 0
        ):
            painter.setRenderHint(
                QPainter.RenderHint.SmoothPixmapTransform,
                not self._interactive_transform,
            )
            rect = self.target_rect()
            if not rect.isEmpty():
                painter.drawPixmap(rect, pixmap)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self._has_image():
            self._begin_interaction()

    def _has_image(self) -> bool:
        return (
            self._preview_pixmap is not None
            and not self._preview_pixmap.isNull()
            and self._source_size.isValid()
        )

    def _required_pixel_size(self) -> QSize:
        rect = self.target_rect()
        dpr = self.devicePixelRatioF()
        return QSize(
            max(1, int(round(rect.width() * dpr))),
            max(1, int(round(rect.height() * dpr))),
        )

    def _full_resolution_needed(self) -> bool:
        if not self._has_image():
            return False
        required = self._required_pixel_size()
        preview_size = self._preview_pixmap.size()
        return (
            required.width() > preview_size.width()
            or required.height() > preview_size.height()
        ) and (
            self._source_size.width() > preview_size.width()
            or self._source_size.height() > preview_size.height()
        )

    def _active_pixmap(self) -> Optional[QPixmap]:
        if self._full_pixmap is not None and self._full_resolution_needed():
            return self._full_pixmap
        return self._preview_pixmap

    def _begin_interaction(self) -> None:
        self._interactive_transform = True
        self._quality_timer.start()

    def _schedule_quality_update(self) -> None:
        if self._has_image() and self._image_path:
            self._quality_timer.start()

    def _finish_interaction(self) -> None:
        self._interactive_transform = False
        self.update()
        if not self._has_image() or not self._image_path:
            return
        if self._zoom_factor <= 1.0:
            self.preview_size_requested.emit(self.preview_bounds())
        elif self._full_pixmap is None and self._full_resolution_needed():
            self.full_resolution_requested.emit()

    # Mouse and wheel event handlers delegated to MouseEventHandler
    def mousePressEvent(self, event: QMouseEvent):
        if not self._mouse_handler.handle_mouse_press(event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._mouse_handler.handle_mouse_move(event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self._mouse_handler.handle_mouse_release(
            event, is_zoomed=(self._zoom_factor > 1.0)
        ):
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if not self._mouse_handler.handle_double_click(event):
            super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if not self._mouse_handler.handle_wheel(event):
            super().wheelEvent(event)


# Backwards compatibility alias
ScaledImageLabel = ImageViewerWidget


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

        # Image viewer as central widget
        self.image_viewer = ImageViewerWidget(self)
        self.viewer = self.image_viewer
        self.image_label = self.image_viewer  # Backwards compatibility alias
        self.setCentralWidget(self.image_viewer)

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

        self._image_pipeline = ImagePipeline(self)
        self._image_pipeline.image_ready.connect(self._on_image_ready)
        self._image_pipeline.image_failed.connect(self._on_image_failed)

        # Keyboard event handler
        self._keyboard_handler = KeyboardEventHandler(
            on_next_image=self.next_image,
            on_prev_image=self.prev_image,
            on_first_image=self.first_image,
            on_last_image=self.last_image,
            on_zoom_in=self.image_viewer.zoom_in,
            on_zoom_out=self.image_viewer.zoom_out,
            on_reset_zoom=self.image_viewer.reset_view,
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
            return self._request_index(requested_index, force=True)
        else:
            self.image_viewer.clear()
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
            self.update_title()
            return False
        return self._request_index(index, force=True)

    def update_title(self):
        """Update window title with [X/Total] counter, filename, dimensions, and zoom."""
        if not self.image_list:
            self.setWindowTitle("Qt Scroll Reader - [0/0] No images found")
            return

        if self._requested_index is not None:
            path = self.image_list[self._requested_index]
            filename = os.path.basename(path)
            self.setWindowTitle(
                f"Qt Scroll Reader - [{self._requested_index + 1}/{len(self.image_list)}] "
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

        zoom_pct = int(round(self.image_viewer.zoom_factor * 100))
        zoom_str = f" - {zoom_pct}%" if zoom_pct != 100 else ""

        self.setWindowTitle(
            f"Qt Scroll Reader - [{self.current_index + 1}/{len(self.image_list)}] {filename}{dim_str}{zoom_str}"
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
        self._image_pipeline.cancel_queued()
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
        self._full_request_pending = True
        self._image_pipeline.request_full(
            self.image_list[self.current_index], self._request_generation
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
            super().keyPressEvent(event)
