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

from .input_controls import CommonViewerControls, MouseEventHandler


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
    page_scroll_requested = pyqtSignal(int, float, float)

    MIN_ZOOM = 0.1
    MAX_ZOOM = 50.0
    QUALITY_DELAY_MS = 100
    WHEEL_SCROLL_PIXELS = 80.0
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

        # Layout options for double page spreads
        self._double_page: bool = False
        self._invert_page_order: bool = False
        self._page_spacing: bool = True
        self.SPACING: int = 10

        # Secondary page attributes for spread display
        self._sec_preview_pixmap: Optional[QPixmap] = None
        self._sec_full_pixmap: Optional[QPixmap] = None
        self._sec_source_size = QSize()
        self._sec_image_path: Optional[str] = None

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
        self._clear_secondary_page()
        self.reset_view()

    def pixmap(self) -> Optional[QPixmap]:
        """Return the pixels currently selected for painting."""
        return self._active_pixmap()

    @property
    def source_size(self) -> QSize:
        """Return original file dimensions, independent of preview resolution."""
        return QSize(self._source_size)

    @property
    def sec_source_size(self) -> QSize:
        """Return original file dimensions for the secondary page in a spread."""
        return QSize(self._sec_source_size)

    @property
    def image_path(self) -> Optional[str]:
        return self._image_path

    @property
    def sec_image_path(self) -> Optional[str]:
        return self._sec_image_path

    def preview_bounds(self) -> QSize:
        """Return viewport dimensions in physical pixels for preview decoding."""
        dpr = self.devicePixelRatioF()
        return QSize(
            max(1, int(round(self.width() * dpr))),
            max(1, int(round(self.height() * dpr))),
        )

    def set_layout_options(
        self,
        *,
        double_page: Optional[bool] = None,
        invert_page_order: Optional[bool] = None,
        page_spacing: Optional[bool] = None,
    ) -> None:
        """Update layout options for double page spreads."""
        if double_page is not None:
            self._double_page = double_page
        if invert_page_order is not None:
            self._invert_page_order = invert_page_order
        if page_spacing is not None:
            self._page_spacing = page_spacing
        self.update()

    def is_spread(self) -> bool:
        """Return True if currently configured and loaded with a two-page spread."""
        has_first = (
            self._preview_pixmap is not None
            and not self._preview_pixmap.isNull()
            and self._source_size.isValid()
        )
        has_sec = (
            self._sec_preview_pixmap is not None
            and not self._sec_preview_pixmap.isNull()
            and self._sec_source_size.isValid()
        )
        return self._double_page and has_first and has_sec

    def _active_sec_pixmap(self) -> Optional[QPixmap]:
        if self._sec_full_pixmap is not None and not self._sec_full_pixmap.isNull():
            return self._sec_full_pixmap
        return self._sec_preview_pixmap

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
        self._clear_secondary_page()
        self._interactive_transform = False
        if reset_view:
            self.reset_view()
            if not self._full_resolution_needed():
                self._quality_timer.stop()
        else:
            self._clamp_pan_offset()
            self._update_pan_cursor()
            self.update()

    def set_spread_preview(
        self,
        first_page: tuple[Optional[QPixmap], QSize, str],
        second_page: Optional[tuple[Optional[QPixmap], QSize, str]] = None,
        reset_view: bool = True,
    ) -> None:
        """Atomically install preview pixmaps for one page or two pages in a spread."""
        pix1, size1, path1 = first_page
        self._preview_pixmap = pix1
        self._full_pixmap = None
        self._source_size = QSize(size1)
        self._image_path = path1

        if second_page is not None:
            pix2, size2, path2 = second_page
            self._sec_preview_pixmap = pix2
            self._sec_full_pixmap = None
            self._sec_source_size = QSize(size2)
            self._sec_image_path = path2
        else:
            self._clear_secondary_page()

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
        updated = False
        if image_path == self._image_path:
            self._preview_pixmap = pixmap
            if self._zoom_factor <= 1.0:
                self._full_pixmap = None
            updated = True
        elif image_path == self._sec_image_path:
            self._sec_preview_pixmap = pixmap
            if self._zoom_factor <= 1.0:
                self._sec_full_pixmap = None
            updated = True
        if updated:
            self.update()

    def set_full_resolution_pixmap(self, pixmap: QPixmap, image_path: str) -> None:
        """Install full pixels for detailed zoom without changing view geometry."""
        updated = False
        if image_path == self._image_path:
            self._full_pixmap = pixmap
            updated = True
        elif image_path == self._sec_image_path:
            self._sec_full_pixmap = pixmap
            updated = True
        if updated:
            self.update()

    def release_full_resolution(self) -> None:
        """Drop the large buffer while retaining the small transition preview."""
        self._full_pixmap = None
        self._sec_full_pixmap = None
        self.update()

    def _clear_secondary_page(self) -> None:
        """Release all state associated with the optional second page."""
        self._sec_preview_pixmap = None
        self._sec_full_pixmap = None
        self._sec_source_size = QSize()
        self._sec_image_path = None

    def release_render_cache(self) -> None:
        """Drop all decoded buffers when this viewer is not the active mode."""
        self._preview_pixmap = None
        self._full_pixmap = None
        self._source_size = QSize()
        self._image_path = None
        self._clear_secondary_page()
        self._quality_timer.stop()
        self.update()

    def clear(self):
        """Clear current image and repaint empty canvas."""
        self._preview_pixmap = None
        self._full_pixmap = None
        self._source_size = QSize()
        self._image_path = None
        self._clear_secondary_page()
        self._quality_timer.stop()
        self.reset_view()

    def reset_view(self):
        """Reset zoom factor and pan offset back to centered fit-to-window."""
        self._zoom_factor = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._full_pixmap = None
        self._sec_full_pixmap = None
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

    def restore_scroll_position(
        self, zoom_factor: float, horizontal_ratio: float, at_top: bool
    ) -> None:
        """Restore a scroll-like position after crossing onto another page."""
        self._zoom_factor = max(self.MIN_ZOOM, min(self.MAX_ZOOM, zoom_factor))
        limits = self._pan_limits()
        self._pan_offset = QPointF(
            max(-1.0, min(1.0, horizontal_ratio)) * limits.x(),
            limits.y() if at_top else -limits.y(),
        )
        self._clamp_pan_offset()
        self._update_pan_cursor()
        self.update()
        self.zoom_changed.emit(self._zoom_factor)
        self._schedule_quality_update()

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
        """Calculate the target rectangle of the image/spread within widget bounds,
        accounting for zoom and pan while preserving aspect ratio.
        """
        if not self._has_image():
            return QRect()

        widget_size = self.size()
        if widget_size.width() <= 0 or widget_size.height() <= 0:
            return QRect()

        if not self.is_spread():
            base_size = self._source_size.scaled(
                widget_size, Qt.AspectRatioMode.KeepAspectRatio
            )
            w = base_size.width() * self._zoom_factor
            h = base_size.height() * self._zoom_factor
            x = (widget_size.width() - w) / 2.0 + self._pan_offset.x()
            y = (widget_size.height() - h) / 2.0 + self._pan_offset.y()
            return QRect(int(round(x)), int(round(y)), int(round(w)), int(round(h)))

        size1 = self._source_size
        size2 = self._sec_source_size
        h_norm = max(size1.height(), size2.height(), 1)
        w1 = size1.width() * (h_norm / max(1, size1.height()))
        w2 = size2.width() * (h_norm / max(1, size2.height()))
        spacing = self.SPACING if self._page_spacing else 0
        w_pages = w1 + w2
        avail_w = max(1.0, widget_size.width() - spacing)

        base_scale = min(
            avail_w / max(1.0, w_pages),
            widget_size.height() / max(1.0, h_norm),
        )
        total_w = w_pages * base_scale * self._zoom_factor + spacing
        total_h = h_norm * base_scale * self._zoom_factor
        x = (widget_size.width() - total_w) / 2.0 + self._pan_offset.x()
        y = (widget_size.height() - total_h) / 2.0 + self._pan_offset.y()
        return QRect(int(round(x)), int(round(y)), int(round(total_w)), int(round(total_h)))

    def target_rects(self) -> list[tuple[QRect, Optional[QPixmap]]]:
        """Return list of (target_rect, pixmap) for each page to draw."""
        if not self._has_image():
            return []

        if not self.is_spread():
            pix = self._active_pixmap()
            rect = self.target_rect()
            return [(rect, pix)] if pix and not rect.isEmpty() else []

        widget_size = self.size()
        if widget_size.width() <= 0 or widget_size.height() <= 0:
            return []

        pix1 = self._active_pixmap()
        pix2 = self._active_sec_pixmap()
        size1 = self._source_size
        size2 = self._sec_source_size

        if self._invert_page_order:
            left_pix, left_size = pix2, size2
            right_pix, right_size = pix1, size1
        else:
            left_pix, left_size = pix1, size1
            right_pix, right_size = pix2, size2

        h_norm = max(size1.height(), size2.height(), 1)
        w_l = left_size.width() * (h_norm / max(1, left_size.height()))
        w_r = right_size.width() * (h_norm / max(1, right_size.height()))
        spacing = self.SPACING if self._page_spacing else 0
        w_pages = w_l + w_r
        avail_w = max(1.0, widget_size.width() - spacing)

        base_scale = min(
            avail_w / max(1.0, w_pages),
            widget_size.height() / max(1.0, h_norm),
        )
        scaled_w_l = w_l * base_scale * self._zoom_factor
        scaled_w_r = w_r * base_scale * self._zoom_factor
        scaled_s = spacing
        scaled_h = h_norm * base_scale * self._zoom_factor
        total_w = scaled_w_l + scaled_s + scaled_w_r

        x = (widget_size.width() - total_w) / 2.0 + self._pan_offset.x()
        y = (widget_size.height() - scaled_h) / 2.0 + self._pan_offset.y()

        rect_l = QRect(int(round(x)), int(round(y)), int(round(scaled_w_l)), int(round(scaled_h)))
        rect_r = QRect(int(round(x + scaled_w_l + scaled_s)), int(round(y)), int(round(scaled_w_r)), int(round(scaled_h)))

        results = []
        if left_pix is not None and not left_pix.isNull() and not rect_l.isEmpty():
            results.append((rect_l, left_pix))
        if right_pix is not None and not right_pix.isNull() and not rect_r.isEmpty():
            results.append((rect_r, right_pix))
        return results

    def paintEvent(self, event):
        """Draw one complete buffered frame using the cheapest suitable pixel source."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))

        if not self._has_image() or self.width() <= 0 or self.height() <= 0:
            return

        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            not self._interactive_transform,
        )
        for rect, pixmap in self.target_rects():
            if pixmap is not None and not pixmap.isNull() and not rect.isEmpty():
                painter.drawPixmap(rect, pixmap)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self._has_image():
            self._clamp_pan_offset()
            self._update_pan_cursor()
            self._begin_interaction()

    def _has_image(self) -> bool:
        has_first = (
            self._preview_pixmap is not None
            and not self._preview_pixmap.isNull()
            and self._source_size.isValid()
        )
        has_sec = (
            self._sec_preview_pixmap is not None
            and not self._sec_preview_pixmap.isNull()
            and self._sec_source_size.isValid()
        )
        return has_first or has_sec

    def _pan_limits(self) -> QPointF:
        """Return maximum centred pan offsets for the current scaled image or spread."""
        if not self._has_image() or self.width() <= 0 or self.height() <= 0:
            return QPointF(0.0, 0.0)

        rect = self.target_rect()
        return QPointF(
            max(0.0, (rect.width() - self.width()) / 2.0),
            max(0.0, (rect.height() - self.height()) / 2.0),
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
        if self._zoom_factor > 1.0 and self._handle_zoomed_wheel(event):
            event.accept()
            return
        if not self._controls.handle_wheel(event):
            super().wheelEvent(event)

    def _handle_zoomed_wheel(self, event: QWheelEvent) -> bool:
        """Pan a zoomed page, crossing pages only beyond a vertical edge."""
        pixel_delta = event.pixelDelta().y()
        angle_delta = event.angleDelta().y()
        if pixel_delta == 0 and angle_delta == 0:
            return False

        scroll_delta = (
            float(pixel_delta)
            if pixel_delta
            else (angle_delta / 120.0) * self.WHEEL_SCROLL_PIXELS
        )
        limits = self._pan_limits()
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+wheel remains the standard zoom gesture.
            return False
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            self.pan_by(scroll_delta, 0.0)
            return True

        at_top = self._pan_offset.y() >= limits.y() - 0.5
        at_bottom = self._pan_offset.y() <= -limits.y() + 0.5
        if (scroll_delta > 0 and at_top) or (scroll_delta < 0 and at_bottom):
            horizontal_ratio = (
                self._pan_offset.x() / limits.x() if limits.x() > 0.0 else 0.0
            )
            direction = -1 if scroll_delta > 0 else 1
            self.page_scroll_requested.emit(
                direction, self._zoom_factor, horizontal_ratio
            )
            return True

        self.pan_by(0.0, scroll_delta)
        return True


# Backwards compatibility alias
ScaledImageLabel = ImageViewerWidget
