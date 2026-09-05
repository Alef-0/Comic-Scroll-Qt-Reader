"""Single image viewer widget implementation using Qt6."""

from typing import Optional

from PyQt6.QtCore import QPointF, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import QWidget

try:
    from src.controls.events import CommonViewerControls, MouseEventHandler
except ImportError:
    from controls.events import CommonViewerControls, MouseEventHandler


class ImageViewerWidget(QWidget):
    """Custom QWidget that uses QPainter to dynamically draw, scale, zoom, and pan
    its image while strictly preserving aspect ratio.
    """

    next_image_requested = pyqtSignal()
    prev_image_requested = pyqtSignal()
    zoom_changed = pyqtSignal(float)
    preview_size_requested = pyqtSignal(QSize)
    full_resolution_requested = pyqtSignal()
    toggle_mode_requested = pyqtSignal()
    mode_single_requested = pyqtSignal()
    mode_scroll_requested = pyqtSignal()

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

        # Common control handler emitting signals that activate viewer functions
        self._controls = CommonViewerControls(self)
        self._controls.connect_viewer(self)
        self._mouse_handler = self._controls  # Backwards compatibility alias

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
        if not self._controls.is_dragging:
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

    # Mouse and wheel event handlers delegated to CommonViewerControls
    def mousePressEvent(self, event: QMouseEvent):
        if not self._controls.handle_mouse_press(event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._controls.handle_mouse_move(event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self._controls.handle_mouse_release(
            event, is_zoomed=(self._zoom_factor > 1.0)
        ):
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if not self._controls.handle_double_click(event):
            super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if not self._controls.handle_wheel(event):
            super().wheelEvent(event)


# Backwards compatibility alias
ScaledImageLabel = ImageViewerWidget
