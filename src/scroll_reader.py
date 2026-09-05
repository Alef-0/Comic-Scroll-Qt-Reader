"""Continuous vertical scroll reader widget using Qt6."""

import os
from typing import Dict, List, Optional, Set

from PyQt6.QtCore import QPointF, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QImageReader,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QShowEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import QAbstractScrollArea

try:
    from src.controls.events import CommonViewerControls
    from src.image_pipeline import DecodeResult, ImagePipeline
except ImportError:
    from controls.events import CommonViewerControls
    from image_pipeline import DecodeResult, ImagePipeline


class ScrollReaderWidget(QAbstractScrollArea):
    """Continuous vertical scroll reader displaying all images in a folder sequentially.

    Key Features:
    - Maintains natural/alphabetical image ordering.
    - Sizing: All images aim to have the exact same width (`target_width`), while each image's
      height strictly preserves its own aspect ratio.
    - Constant vertical spacing between images.
    - Virtualized rendering: Only visible and near-visible images are loaded into memory,
      enabling instant loading and smooth 60fps scrolling across hundreds of pages.
    - Anchored zooming via Ctrl+Wheel, Ctrl++/--, or reset via Ctrl+0.
    - Drag-to-pan navigation with left mouse button.
    - Mode switching via Key 1, Key 2, and right mouse click.
    """

    visible_image_changed = pyqtSignal(int)
    zoom_changed = pyqtSignal(float)
    toggle_mode_requested = pyqtSignal()
    mode_single_requested = pyqtSignal()
    mode_scroll_requested = pyqtSignal()

    SPACING = 10
    MIN_ZOOM = 0.1
    MAX_ZOOM = 20.0
    SCROLL_STEP = 60

    def __init__(self, parent=None, pipeline: Optional[ImagePipeline] = None):
        super().__init__(parent)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Style scrollbar area
        self.setStyleSheet(
            "QAbstractScrollArea { background-color: #1a1a1a; border: none; }"
            "QScrollBar:vertical { background: #1a1a1a; width: 14px; margin: 0px; }"
            "QScrollBar::handle:vertical { background: #3a3a3a; min-height: 30px; border-radius: 4px; }"
            "QScrollBar::handle:vertical:hover { background: #555555; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
            "QScrollBar:horizontal { background: #1a1a1a; height: 14px; margin: 0px; }"
            "QScrollBar::handle:horizontal { background: #3a3a3a; min-width: 30px; border-radius: 4px; }"
            "QScrollBar::handle:horizontal:hover { background: #555555; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { height: 0px; }"
        )

        self._pipeline = pipeline
        self._owns_pipeline = False
        if self._pipeline is None:
            self._pipeline = ImagePipeline(self)
            self._owns_pipeline = True

        self._pipeline.image_ready.connect(self._on_image_ready)
        self._pipeline.image_failed.connect(self._on_image_failed)

        self._image_list: List[str] = []
        self._image_sizes: Dict[str, QSize] = {}
        self._image_rects: List[QRect] = []
        self._pixmaps: Dict[int, QPixmap] = {}
        self._decoded_bounds: Dict[int, QSize] = {}
        self._pending_requests: Dict[int, Dict[tuple[int, int], int]] = {}
        self._requested_indices: Set[int] = set()
        self._failed_indices: Set[int] = set()

        self._zoom_factor: float = 1.0
        self._current_visible_index: int = 0
        self._pending_scroll_index: Optional[int] = None

        # Common control handler emitting signals that activate viewer functions
        self._controls = CommonViewerControls(self)
        self._controls.connect_viewer(self)

        # Connect scrollbar signals
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewport().update())

    def setCursor(self, cursor: Qt.CursorShape) -> None:
        super().setCursor(cursor)
        self.viewport().setCursor(cursor)

    def pan_by(self, delta_x: float, delta_y: float) -> None:
        """Translate the scroll view by delta offsets."""
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - int(round(delta_y))
        )
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - int(round(delta_x))
        )

    def zoom_at(self, scale_factor: float, anchor_pos: Optional[QPointF] = None) -> None:
        """Scale zoom factor anchored at a given widget position."""
        self.set_zoom(self._zoom_factor * scale_factor, anchor_pos)

    def reset_view(self) -> None:
        """Reset view zoom to default."""
        self.reset_zoom()

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    @property
    def image_list(self) -> List[str]:
        return list(self._image_list)

    @property
    def image_rects(self) -> List[QRect]:
        return list(self._image_rects)

    def current_visible_index(self) -> int:
        return self._current_visible_index

    def set_images(self, image_list: List[str], start_index: int = 0) -> None:
        """Set image list and initialize layout, scrolling to start_index."""
        self._cancel_pending_requests()
        self._image_list = list(image_list)
        self._pixmaps.clear()
        self._decoded_bounds.clear()
        self._pending_requests.clear()
        self._requested_indices.clear()
        self._failed_indices.clear()

        # Cache source dimensions
        for path in self._image_list:
            self._get_source_size(path)

        self._relayout()

        if 0 <= start_index < len(self._image_list):
            self.scroll_to_index(start_index)
        else:
            self.scroll_to_index(0)

    def clear(self) -> None:
        """Clear all images and reset layout."""
        self._cancel_pending_requests()
        self._image_list.clear()
        self._image_rects.clear()
        self._pixmaps.clear()
        self._decoded_bounds.clear()
        self._pending_requests.clear()
        self._requested_indices.clear()
        self._failed_indices.clear()
        self._current_visible_index = 0
        self._pending_scroll_index = None
        self.verticalScrollBar().setRange(0, 0)
        self.horizontalScrollBar().setRange(0, 0)
        self.viewport().update()

    def scroll_to_index(self, index: int) -> None:
        """Scroll vertical view directly so image at index starts at the top."""
        if not self._image_rects or not (0 <= index < len(self._image_rects)):
            self._pending_scroll_index = index
            return

        self._pending_scroll_index = None
        target_y = self._image_rects[index].y()
        self.verticalScrollBar().setValue(target_y)
        self._current_visible_index = index
        self.visible_image_changed.emit(index)
        self._update_visible_images()
        self.viewport().update()

    def set_zoom(self, zoom_factor: float, anchor_pos: Optional[QPointF] = None) -> None:
        """Set zoom factor, preserving anchor position stationary in viewport."""
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, zoom_factor))
        if abs(new_zoom - self._zoom_factor) < 1e-6:
            return

        vp_w = self.viewport().width()
        vp_h = self.viewport().height()

        # Default anchor to center of viewport
        if anchor_pos is None:
            ax = vp_w / 2.0
            ay = vp_h / 2.0
        else:
            ax = anchor_pos.x()
            ay = anchor_pos.y()

        cur_scroll_x = self.horizontalScrollBar().value()
        cur_scroll_y = self.verticalScrollBar().value()
        content_anchor_x = cur_scroll_x + ax
        content_anchor_y = cur_scroll_y + ay

        old_zoom = self._zoom_factor
        zoom_ratio = new_zoom / old_zoom

        self._zoom_factor = new_zoom
        self._relayout()

        # Maintain stationary anchor point
        new_content_x = content_anchor_x * zoom_ratio
        new_content_y = content_anchor_y * zoom_ratio

        new_scroll_x = int(round(new_content_x - ax))
        new_scroll_y = int(round(new_content_y - ay))

        self.horizontalScrollBar().setValue(new_scroll_x)
        self.verticalScrollBar().setValue(new_scroll_y)

        self.zoom_changed.emit(self._zoom_factor)
        self._update_visible_images()
        self.viewport().update()

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom_factor * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom_factor * 0.8)

    def reset_zoom(self) -> None:
        self.set_zoom(1.0)

    def _get_source_size(self, path: str) -> QSize:
        """Query and cache native dimensions of image via header metadata."""
        if path in self._image_sizes:
            return self._image_sizes[path]

        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid() or size.width() <= 0 or size.height() <= 0:
            # Fallback size if header unreadable
            size = QSize(800, 1200)

        self._image_sizes[path] = size
        return size

    def _relayout(self) -> None:
        """Compute layout: all images share uniform width while preserving aspect ratios."""
        if not self._image_list:
            self._image_rects.clear()
            self.verticalScrollBar().setRange(0, 0)
            self.horizontalScrollBar().setRange(0, 0)
            return

        vp_w = self.viewport().width()
        vp_h = self.viewport().height()
        if vp_w <= 0:
            vp_w = self.width() if self.width() > 0 else 1280
        if vp_h <= 0:
            vp_h = self.height() if self.height() > 0 else 720

        # Uniform width across all images: target_width
        target_width = max(50, int(round(vp_w * self._zoom_factor)))

        self._image_rects = []
        current_y = 0

        for path in self._image_list:
            src_size = self._get_source_size(path)
            src_w = max(1, src_size.width())
            src_h = max(1, src_size.height())

            img_w = target_width
            # Height preserves native aspect ratio
            img_h = max(1, int(round(target_width * (src_h / src_w))))

            # Horizontal placement: centered when narrower than viewport
            if target_width < vp_w:
                img_x = (vp_w - target_width) // 2
            else:
                img_x = 0

            rect = QRect(img_x, current_y, img_w, img_h)
            self._image_rects.append(rect)
            current_y += img_h + self.SPACING

        total_content_h = max(0, current_y - self.SPACING if self._image_rects else 0)
        total_content_w = target_width

        # Update scrollbar ranges
        max_v_scroll = max(0, total_content_h - vp_h)
        self.verticalScrollBar().setRange(0, max_v_scroll)
        self.verticalScrollBar().setPageStep(vp_h)
        self.verticalScrollBar().setSingleStep(self.SCROLL_STEP)

        if total_content_w > vp_w:
            self.horizontalScrollBar().setRange(0, total_content_w - vp_w)
            self.horizontalScrollBar().setPageStep(vp_w)
            self.horizontalScrollBar().setSingleStep(self.SCROLL_STEP)
        else:
            self.horizontalScrollBar().setRange(0, 0)

    def _on_scroll_changed(self, value: int) -> None:
        """Handle scroll position change: detect current reading image and request previews."""
        if not self._image_rects:
            return

        vp_h = self.viewport().height()
        read_line = value + min(80, vp_h // 4)

        # Detect which image is at reading line
        current_index = 0
        for i, rect in enumerate(self._image_rects):
            if rect.y() <= read_line < rect.y() + rect.height() + self.SPACING:
                current_index = i
                break
            elif rect.y() > read_line:
                break
            current_index = i

        if current_index != self._current_visible_index:
            self._current_visible_index = current_index
            self.visible_image_changed.emit(current_index)

        self._update_visible_images()
        self.viewport().update()

    def _update_visible_images(self) -> None:
        """Request correctly sized previews and keep pending work near the viewport."""
        if not self._image_rects or not self._pipeline:
            return

        scroll_y = self.verticalScrollBar().value()
        vp_h = self.viewport().height()
        vp_bottom = scroll_y + vp_h

        visible_indices = []
        for i, rect in enumerate(self._image_rects):
            if rect.y() + rect.height() >= scroll_y and rect.y() <= vp_bottom:
                visible_indices.append(i)

        if not visible_indices:
            visible_indices = [self._current_visible_index]

        min_vis = min(visible_indices)
        max_vis = max(visible_indices)

        # Prefetch window: 1 above, 2 below
        prefetch_min = max(0, min_vis - 1)
        prefetch_max = min(len(self._image_list) - 1, max_vis + 2)
        wanted_indices = set(range(prefetch_min, prefetch_max + 1))

        # Fast scrolling must not leave an ever-growing low-priority queue. Drop
        # consumers which have moved outside the prefetch window; running image
        # reads may finish internally, but their stale result is not delivered.
        distant_pending = self._requested_indices - wanted_indices
        if distant_pending:
            self._pipeline.cancel_queued(
                {f"scroll-{idx}" for idx in distant_pending}
            )
            for idx in distant_pending:
                self._pending_requests.pop(idx, None)
                self._requested_indices.discard(idx)

        dpr = self.devicePixelRatioF()

        for idx in range(prefetch_min, prefetch_max + 1):
            rect = self._image_rects[idx]
            target_bounds = QSize(
                max(1, int(round(rect.width() * dpr))),
                max(1, int(round(rect.height() * dpr))),
            )
            priority = 2 if (min_vis <= idx <= max_vis) else 0

            decoded_bounds = self._decoded_bounds.get(idx)
            if decoded_bounds is not None and self._bounds_cover(
                decoded_bounds, target_bounds
            ):
                continue

            pending = self._pending_requests.setdefault(idx, {})
            covering_key = next(
                (
                    key
                    for key in pending
                    if self._bounds_cover(QSize(*key), target_bounds)
                ),
                None,
            )
            if covering_key is not None:
                if priority > pending[covering_key]:
                    queued_bounds = QSize(*covering_key)
                    self._pipeline.promote_queued(
                        self._image_list[idx], queued_bounds, priority
                    )
                    pending[covering_key] = priority
                continue

            bounds_key = (target_bounds.width(), target_bounds.height())
            pending[bounds_key] = priority
            self._requested_indices.add(idx)
            self._pipeline.request_preview(
                self._image_list[idx],
                target_bounds,
                request_id=idx,
                purpose=f"scroll-{idx}",
                priority=priority,
            )

        # Prune distant cached pixmaps to bound memory usage
        retained_range = set(range(max(0, min_vis - 5), min(len(self._image_list), max_vis + 6)))
        for idx in list(self._pixmaps.keys()):
            if idx not in retained_range:
                del self._pixmaps[idx]
                self._decoded_bounds.pop(idx, None)

    @staticmethod
    def _bounds_cover(available: QSize, required: QSize) -> bool:
        return (
            available.width() >= required.width()
            and available.height() >= required.height()
        )

    def _finish_pending_request(self, idx: int, bounds: Optional[QSize]) -> None:
        if bounds is not None:
            pending = self._pending_requests.get(idx)
            if pending is not None:
                pending.pop((bounds.width(), bounds.height()), None)
                if not pending:
                    self._pending_requests.pop(idx, None)
        if idx not in self._pending_requests:
            self._requested_indices.discard(idx)

    def _cancel_pending_requests(self) -> None:
        if self._pipeline is not None and self._requested_indices:
            self._pipeline.cancel_queued(
                {f"scroll-{idx}" for idx in self._requested_indices}
            )

    def _on_image_ready(self, result: DecodeResult) -> None:
        """Receive decoded preview from ImagePipeline and repaint."""
        request = result.request
        if not request.purpose.startswith("scroll-"):
            return

        idx = request.request_id
        if not (
            0 <= idx < len(self._image_list)
            and self._image_list[idx] == request.path
        ):
            return

        self._finish_pending_request(idx, request.bounds)
        self._failed_indices.discard(idx)

        fulfilled_bounds = (
            QSize(request.bounds)
            if request.bounds is not None
            else result.image.size()
        )
        current_bounds = self._decoded_bounds.get(idx)
        if current_bounds is None or self._bounds_cover(
            fulfilled_bounds, current_bounds
        ):
            self._pixmaps[idx] = QPixmap.fromImage(result.image)
            self._decoded_bounds[idx] = fulfilled_bounds
        self.viewport().update()

    def _on_image_failed(self, result: DecodeResult) -> None:
        """Handle decode failure."""
        request = result.request
        if not request.purpose.startswith("scroll-"):
            return

        idx = request.request_id
        if not (
            0 <= idx < len(self._image_list)
            and self._image_list[idx] == request.path
        ):
            return

        self._finish_pending_request(idx, request.bounds)
        if idx not in self._pixmaps and idx not in self._pending_requests:
            self._failed_indices.add(idx)
        self.viewport().update()

    def paintEvent(self, event) -> None:
        """Paint visible images and placeholders onto the viewport."""
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), QColor("#1a1a1a"))

        if not self._image_rects:
            painter.setPen(QColor("#888888"))
            painter.drawText(
                self.viewport().rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No images to display",
            )
            return

        scroll_x = self.horizontalScrollBar().value()
        scroll_y = self.verticalScrollBar().value()
        vp_h = self.viewport().height()
        vp_bottom = scroll_y + vp_h

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        for i, rect in enumerate(self._image_rects):
            # Check vertical intersection with viewport
            if rect.y() + rect.height() < scroll_y or rect.y() > vp_bottom:
                continue

            screen_x = rect.x() - scroll_x
            screen_y = rect.y() - scroll_y
            screen_rect = QRect(screen_x, screen_y, rect.width(), rect.height())

            if i in self._pixmaps:
                painter.drawPixmap(screen_rect, self._pixmaps[i])
            elif i in self._failed_indices:
                painter.fillRect(screen_rect, QColor("#331a1a"))
                painter.setPen(QColor("#ff5555"))
                painter.drawText(
                    screen_rect,
                    Qt.AlignmentFlag.AlignCenter,
                    f"Failed to load Page {i + 1}",
                )
            else:
                # Placeholder with subtle border and text
                painter.fillRect(screen_rect, QColor("#222222"))
                painter.setPen(QColor("#2d2d2d"))
                painter.drawRect(screen_rect)
                painter.setPen(QColor("#666666"))
                painter.drawText(
                    screen_rect,
                    Qt.AlignmentFlag.AlignCenter,
                    f"Page {i + 1}",
                )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout()
        if self._pending_scroll_index is not None:
            self.scroll_to_index(self._pending_scroll_index)
        else:
            # Maintain active image in view
            if 0 <= self._current_visible_index < len(self._image_rects):
                self._update_visible_images()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._relayout()
        if self._pending_scroll_index is not None:
            self.scroll_to_index(self._pending_scroll_index)
        else:
            self._update_visible_images()

    # Mouse and wheel controls handled via CommonViewerControls
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._controls.handle_mouse_press(event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._controls.handle_mouse_move(event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._controls.handle_mouse_release(
            event, is_zoomed=(self._zoom_factor > 1.0)
        ):
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self._controls.handle_double_click(event):
            super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        modifiers = event.modifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        if is_ctrl:
            if not self._controls.handle_wheel(event, handle_navigation=False):
                super().wheelEvent(event)
        else:
            delta_y = event.angleDelta().y()
            if delta_y != 0:
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - delta_y
                )
                event.accept()
            else:
                super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)

        # Mode switching shortcuts
        if not is_ctrl:
            if key == Qt.Key.Key_1:
                self.mode_single_requested.emit()
                event.accept()
                return
            elif key == Qt.Key.Key_2:
                self.mode_scroll_requested.emit()
                event.accept()
                return

        # Zoom shortcuts (with Ctrl)
        if is_ctrl:
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.zoom_in()
                event.accept()
                return
            elif key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
                self.zoom_out()
                event.accept()
                return
            elif key in (Qt.Key.Key_0, Qt.Key.Key_ParenRight):
                self.reset_zoom()
                event.accept()
                return

        # Navigation keys (without Ctrl)
        if not is_ctrl:
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() + self.SCROLL_STEP
                )
                event.accept()
                return
            elif key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - self.SCROLL_STEP
                )
                event.accept()
                return
            elif key in (Qt.Key.Key_PageDown, Qt.Key.Key_Space):
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() + self.viewport().height()
                )
                event.accept()
                return
            elif key in (Qt.Key.Key_PageUp, Qt.Key.Key_Backspace):
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - self.viewport().height()
                )
                event.accept()
                return
            elif key == Qt.Key.Key_Home:
                self.verticalScrollBar().setValue(0)
                event.accept()
                return
            elif key == Qt.Key.Key_End:
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                event.accept()
                return

        super().keyPressEvent(event)
