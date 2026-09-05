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
    DETAIL_BUFFER_BYTES = 64 * 1024 * 1024

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
            self._clamp_pan_offset()
            self._update_pan_cursor()
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

    def release_render_cache(self) -> None:
        """Drop all decoded buffers when this viewer is not the active mode."""
        self._preview_pixmap = None
        self._full_pixmap = None
        self._source_size = QSize()
        self._image_path = None
        self._quality_timer.stop()
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
        """Pan only across overflowing pixels without exposing empty canvas."""
        if not self._can_pan():
            return

        previous_offset = QPointF(self._pan_offset)
        self._pan_offset += QPointF(delta_x, delta_y)
        self._clamp_pan_offset()
        if self._pan_offset == previous_offset:
            return

        self._begin_interaction()
        self.update()

    def zoom_at(self, scale_factor: float, anchor_pos: Optional[QPointF] = None):
        """Zoom around the viewport centre while preserving aspect ratio."""
        if not self._has_image():
            return

        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom_factor * scale_factor))
        if abs(new_zoom - self._zoom_factor) < 1e-6:
            return

        zoom_ratio = new_zoom / self._zoom_factor
        self._pan_offset = QPointF(
            self._pan_offset.x() * zoom_ratio,
            self._pan_offset.y() * zoom_ratio,
        )
        self._zoom_factor = new_zoom
        self._clamp_pan_offset()
        self._begin_interaction()

        # Only advertise dragging when at least one image axis overflows.
        self._update_pan_cursor()

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
            self._clamp_pan_offset()
            self._update_pan_cursor()
            self._begin_interaction()

    def _has_image(self) -> bool:
        return (
            self._preview_pixmap is not None
            and not self._preview_pixmap.isNull()
            and self._source_size.isValid()
        )

    def _pan_limits(self) -> QPointF:
        """Return maximum centred pan offsets for the current scaled image."""
        if not self._has_image() or self.width() <= 0 or self.height() <= 0:
            return QPointF(0.0, 0.0)

        base_size = self._source_size.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        scaled_width = base_size.width() * self._zoom_factor
        scaled_height = base_size.height() * self._zoom_factor
        return QPointF(
            max(0.0, (scaled_width - self.width()) / 2.0),
            max(0.0, (scaled_height - self.height()) / 2.0),
        )

    def _can_pan(self) -> bool:
        limits = self._pan_limits()
        return limits.x() > 0.0 or limits.y() > 0.0

    def _clamp_pan_offset(self) -> None:
        limits = self._pan_limits()
        self._pan_offset = QPointF(
            max(-limits.x(), min(limits.x(), self._pan_offset.x())),
            max(-limits.y(), min(limits.y(), self._pan_offset.y())),
        )

    def _update_pan_cursor(self) -> None:
        if not self._controls.is_dragging:
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._can_pan()
                else Qt.CursorShape.ArrowCursor
            )

    def _required_pixel_size(self) -> QSize:
        rect = self.target_rect()
        dpr = self.devicePixelRatioF()
        return QSize(
            max(1, int(round(rect.width() * dpr))),
            max(1, int(round(rect.height() * dpr))),
        )

    def detail_bounds(self) -> QSize:
        """Return the useful zoom decode size, capped by the detail byte budget."""
        if not self._has_image():
            return QSize()

        desired = self._source_size.scaled(
            self._required_pixel_size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        if (
            desired.width() > self._source_size.width()
            or desired.height() > self._source_size.height()
        ):
            desired = QSize(self._source_size)

        estimated_bytes = desired.width() * desired.height() * 4
        if estimated_bytes > self.DETAIL_BUFFER_BYTES:
            scale = (self.DETAIL_BUFFER_BYTES / estimated_bytes) ** 0.5
            desired = QSize(
                max(1, int(desired.width() * scale)),
                max(1, int(desired.height() * scale)),
            )
        return desired

    def _full_resolution_needed(self) -> bool:
        if not self._has_image():
            return False
        required = self.detail_bounds()
        preview_size = self._preview_pixmap.size()
        return (
            required.width() > preview_size.width()
            or required.height() > preview_size.height()
        )

    def _detail_pixmap_covers_request(self) -> bool:
        if self._full_pixmap is None:
            return False
        required = self.detail_bounds()
        return (
            self._full_pixmap.width() >= required.width()
            and self._full_pixmap.height() >= required.height()
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
        elif (
            self._full_resolution_needed()
            and not self._detail_pixmap_covers_request()
        ):
            self.full_resolution_requested.emit()

    # Mouse and wheel event handlers delegated to CommonViewerControls
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and not self._can_pan():
            super().mousePressEvent(event)
            return
        if not self._controls.handle_mouse_press(event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._controls.handle_mouse_move(event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self._controls.handle_mouse_release(
            event, is_zoomed=self._can_pan()
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
