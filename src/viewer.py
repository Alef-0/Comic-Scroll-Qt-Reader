"""Image Viewer widget and main window implementation using Qt6."""

import os
import re
import sys
from typing import List, Optional

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QMessageBox
from PyQt6.QtGui import QPixmap, QPainter, QColor, QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtCore import Qt, QRect, QPointF, pyqtSignal

# Import controls handlers
try:
    from src.controls.events import KeyboardEventHandler, MouseEventHandler
except ImportError:
    from controls.events import KeyboardEventHandler, MouseEventHandler

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

    MIN_ZOOM = 0.1
    MAX_ZOOM = 50.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)  # Allows window to shrink freely without getting blocked
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #1a1a1a;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pixmap: Optional[QPixmap] = None
        self._image_path: Optional[str] = None
        self._zoom_factor: float = 1.0
        self._pan_offset: QPointF = QPointF(0.0, 0.0)

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
        """Store source pixmap, reset view, and request repaint."""
        self._pixmap = pixmap
        self.reset_view()

    def pixmap(self) -> Optional[QPixmap]:
        """Return source unscaled pixmap."""
        return self._pixmap

    def load_image(self, file_path: str) -> bool:
        """Load image from disk into pixmap."""
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            return False
        self._image_path = file_path
        self.set_pixmap(pixmap)
        return True

    def clear(self):
        """Clear current image and repaint empty canvas."""
        self._pixmap = None
        self._image_path = None
        self.reset_view()

    def reset_view(self):
        """Reset zoom factor and pan offset back to centered fit-to-window."""
        self._zoom_factor = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        self.zoom_changed.emit(self._zoom_factor)

    def pan_by(self, delta_x: float, delta_y: float):
        """Translate the image by a given delta offset."""
        self._pan_offset += QPointF(delta_x, delta_y)
        self.update()

    def zoom_at(self, scale_factor: float, anchor_pos: Optional[QPointF] = None):
        """Zoom in or out anchored around a specific widget coordinate, preserving aspect ratio."""
        if self._pixmap is None or self._pixmap.isNull():
            return

        w_size = self.size()
        if w_size.width() <= 0 or w_size.height() <= 0:
            return

        base_size = self._pixmap.size().scaled(
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
        if self._pixmap is None or self._pixmap.isNull():
            return QRect()

        widget_size = self.size()
        if widget_size.width() <= 0 or widget_size.height() <= 0:
            return QRect()

        base_size = self._pixmap.size().scaled(
            widget_size, Qt.AspectRatioMode.KeepAspectRatio
        )
        w = base_size.width() * self._zoom_factor
        h = base_size.height() * self._zoom_factor
        x = (widget_size.width() - w) / 2.0 + self._pan_offset.x()
        y = (widget_size.height() - h) / 2.0 + self._pan_offset.y()

        return QRect(int(round(x)), int(round(y)), int(round(w)), int(round(h)))

    def paintEvent(self, event):
        """Draw background and scale unscaled pixmap directly onto canvas via QPainter."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))

        if (
            self._pixmap is not None
            and not self._pixmap.isNull()
            and self.width() > 0
            and self.height() > 0
        ):
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            rect = self.target_rect()
            if not rect.isEmpty():
                painter.drawPixmap(rect, self._pixmap)

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

        if initial_file:
            init_abs = os.path.abspath(initial_file)
            if init_abs not in self.image_list and os.path.isfile(init_abs):
                self.image_list.append(init_abs)
                self.image_list.sort(key=natural_sort_key)

            try:
                self.current_index = self.image_list.index(init_abs)
            except ValueError:
                self.current_index = 0 if self.image_list else -1
        else:
            self.current_index = 0 if self.image_list else -1

        if self.image_list and self.current_index >= 0:
            return self.load_current_image()
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
        """Load the image at current_index and update title."""
        if not self.image_list or not (0 <= self.current_index < len(self.image_list)):
            self.image_viewer.clear()
            self.update_title()
            return False

        path = self.image_list[self.current_index]
        if not self.image_viewer.load_image(path):
            QMessageBox.critical(
                self,
                "Error Loading Image",
                f"Could not load image:\n{path}\n\nPlease check the file path and format.",
            )
            self.update_title()
            return False

        self.update_title()
        return True

    def update_title(self):
        """Update window title with [X/Total] counter, filename, dimensions, and zoom."""
        if not self.image_list or self.current_index < 0:
            self.setWindowTitle("Qt Scroll Reader - [0/0] No images found")
            return

        path = self.image_list[self.current_index]
        filename = os.path.basename(path)
        pixmap = self.image_viewer.pixmap()
        dim_str = f" ({pixmap.width()}x{pixmap.height()})" if pixmap and not pixmap.isNull() else ""

        zoom_pct = int(round(self.image_viewer.zoom_factor * 100))
        zoom_str = f" - {zoom_pct}%" if zoom_pct != 100 else ""

        self.setWindowTitle(
            f"Qt Scroll Reader - [{self.current_index + 1}/{len(self.image_list)}] {filename}{dim_str}{zoom_str}"
        )

    def next_image(self):
        """Navigate to next image in alphabetical order."""
        if self.image_list and self.current_index < len(self.image_list) - 1:
            self.go_to_index(self.current_index + 1)

    def prev_image(self):
        """Navigate to previous image in alphabetical order."""
        if self.image_list and self.current_index > 0:
            self.go_to_index(self.current_index - 1)

    def first_image(self):
        """Navigate to the first image."""
        if self.image_list:
            self.go_to_index(0)

    def last_image(self):
        """Navigate to the last image."""
        if self.image_list:
            self.go_to_index(len(self.image_list) - 1)

    def go_to_index(self, index: int):
        """Go directly to image at given index."""
        if 0 <= index < len(self.image_list) and index != self.current_index:
            self.current_index = index
            self.load_current_image()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard navigation and shortcuts."""
        if not self._keyboard_handler.handle_key_press(event):
            super().keyPressEvent(event)
