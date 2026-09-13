"""Floating reader-controls HUD for Comic Scroll Reader."""

from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSlider,
    QToolButton,
    QWidget,
)


class ThumbnailListWidget(QListWidget):
    """Thumbnail list that keeps the companion HUD open while hovered."""

    pointer_entered = pyqtSignal()
    pointer_left = pyqtSignal()

    def enterEvent(self, event):
        self.pointer_entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.pointer_left.emit()
        super().leaveEvent(event)


class ViewerHud(QWidget):
    """Floating HUD overlay positioned at either edge of the viewer window.

    Provides quick visual access to page navigation, mode switching, zoom levels,
    fullscreen, and an optional lazy thumbnail strip, with auto-hiding after
    inactivity.
    """

    prev_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    jump_clicked = pyqtSignal()
    mode_toggled = pyqtSignal()
    zoom_in_clicked = pyqtSignal()
    zoom_out_clicked = pyqtSignal()
    zoom_reset_clicked = pyqtSignal()
    fullscreen_toggled = pyqtSignal()
    comic_mode_selected = pyqtSignal(str)
    thumbnails_toggled = pyqtSignal(bool)
    thumbnail_requested = pyqtSignal(int)
    thumbnail_clicked = pyqtSignal(int)
    hud_scale_changed = pyqtSignal(int)

    HIDE_DELAY_MS = 900
    FADE_DURATION_MS = 350
    ACTIVATION_MARGIN = 28
    EDGE_MARGIN = 24
    MIN_RESPONSIVE_SCALE_PERCENT = 55
    THUMBNAIL_STRIP_WIDTH = 880
    THUMBNAIL_FILMSTRIP_HEIGHT = 206
    THUMBNAIL_SIDEBAR_WIDTH = 174
    THUMBNAIL_DECODE_SIZE = QSize(220, 240)
    THUMBNAIL_ICON_SIZE = QSize(140, 184)
    THUMBNAIL_GRID_SIZE = QSize(154, 198)
    VERTICAL_VISIBLE_COUNT = 5
    HORIZONTAL_VISIBLE_COUNT = 6
    COMIC_MODE_LABELS = {
        "default": "⚙ Default",
        "comics": "📚 Comics",
        "manga": "📖 Manga",
        "webtoon": "📱 Webtoon",
        "custom": "🛠 Custom",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._is_mouse_inside = False
        self._is_pointer_in_activation_band = False
        self._is_pointer_in_thumbnail_band = False
        self._fade_target_visible = False
        self._at_top = False
        self._thumbnail_layout = "vertical"
        self._hud_scale_percent = 100
        self._effective_hud_scale_percent = 100
        self._is_adjusting_hud_scale = False
        self._page_count = 0
        self._display_total_pages = 0
        self._current_thumbnail_index = -1
        self._thumbnail_items_populated = False
        self._thumbnail_requested_indices: set[int] = set()
        self._thumbnail_pixmaps: dict[int, QPixmap] = {}
        self._thumbnail_source_images: dict[int, QImage] = {}
        self._thumbnail_grid_size = QSize(self.THUMBNAIL_GRID_SIZE)
        self._thumbnail_render_size = QSize(self.THUMBNAIL_ICON_SIZE)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_animation = QPropertyAnimation(
            self._opacity_effect, b"opacity", self
        )
        self._fade_animation.setDuration(self.FADE_DURATION_MS)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade_animation.finished.connect(self._finish_fade)

        # Inactivity auto-hide timer
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(self.HIDE_DELAY_MS)
        self._hide_timer.timeout.connect(self._auto_hide)

        self._init_ui()
        self._refresh_layout_geometry()
        QTimer.singleShot(0, self._refresh_layout_geometry)

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Background container pill
        self.pill = QFrame(self)
        self.pill.setObjectName("hudPill")
        self.pill.setStyleSheet(
            "#hudPill {"
            "  background-color: rgba(26, 26, 26, 0.90);"
            "  border: 1px solid rgba(255, 255, 255, 0.15);"
            "  border-radius: 8px;"
            "}"
            "QPushButton, QToolButton {"
            "  background: transparent;"
            "  color: #e0e0e0;"
            "  font-size: 13px;"
            "  font-weight: 500;"
            "  border: none;"
            "  border-radius: 4px;"
            "  padding: 4px 8px;"
            "  min-height: 24px;"
            "}"
            "QPushButton:hover, QToolButton:hover {"
            "  background-color: rgba(255, 255, 255, 0.15);"
            "  color: #ffffff;"
            "}"
            "QPushButton:pressed, QToolButton:pressed {"
            "  background-color: rgba(255, 255, 255, 0.25);"
            "}"
            "QPushButton#thumbnailToggle:checked {"
            "  background-color: rgba(74, 144, 226, 0.18);"
            "  border: 2px solid #4a90e2;"
            "}"
            "QPushButton:disabled, QToolButton:disabled {"
            "  color: #555555;"
            "}"
            "QLabel {"
            "  color: #888888;"
            "  font-size: 13px;"
            "}"
            "QSlider::groove:horizontal {"
            "  height: 4px;"
            "  background: #555b66;"
            "  border-radius: 2px;"
            "}"
            "QSlider::sub-page:horizontal {"
            "  background: #8ab4f8;"
            "  border-radius: 2px;"
            "}"
            "QSlider::handle:horizontal {"
            "  width: 12px;"
            "  margin: -4px 0;"
            "  background: #e0e0e0;"
            "  border: 1px solid #8ab4f8;"
            "  border-radius: 6px;"
            "}"
        )

        pill_layout = QHBoxLayout(self.pill)
        pill_layout.setContentsMargins(10, 5, 10, 5)
        pill_layout.setSpacing(6)

        self.btn_prev = QPushButton("◀", self.pill)
        self.btn_prev.setToolTip("Previous page (Left/Up)")
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.clicked.connect(self.prev_clicked.emit)
        pill_layout.addWidget(self.btn_prev)

        # Page indicator (clickable to jump)
        self.btn_page = QPushButton("Page 1 / 1", self.pill)
        self.btn_page.setToolTip("Click to jump to page (Ctrl+G)")
        self.btn_page.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page.setStyleSheet("font-weight: bold; padding: 4px 10px; color: #ffffff;")
        self.btn_page.clicked.connect(self.jump_clicked.emit)
        pill_layout.addWidget(self.btn_page)

        # Navigation: Next
        self.btn_next = QPushButton("▶", self.pill)
        self.btn_next.setToolTip("Next page (Right/Down/D/S at a page edge)")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.clicked.connect(self.next_clicked.emit)
        pill_layout.addWidget(self.btn_next)

        # Separator
        pill_layout.addWidget(self._make_separator())

        # Mode switch button
        self.btn_mode = QPushButton("📜 Scroll", self.pill)
        self.btn_mode.setToolTip("Switch view mode (1: Single, 2: Continuous Scroll)")
        self.btn_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode.clicked.connect(self.mode_toggled.emit)
        pill_layout.addWidget(self.btn_mode)

        # Separator
        pill_layout.addWidget(self._make_separator())

        self.btn_comic_mode = QToolButton(self.pill)
        self.btn_comic_mode.setText(self.COMIC_MODE_LABELS["default"])
        self.btn_comic_mode.setToolTip("Choose a comic reading layout")
        self.btn_comic_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_comic_mode.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._comic_menu = QMenu(self.btn_comic_mode)
        self._comic_menu.setStyleSheet(
            "QMenu { background-color: #2b2b2b; color: #e0e0e0; "
            "border: 1px solid #444; }"
            "QMenu::item { padding: 6px 24px 6px 20px; }"
            "QMenu::item:selected { background-color: #4a90e2; color: #fff; }"
        )
        for mode in ("default", "comics", "manga", "webtoon"):
            action = self._comic_menu.addAction(self.COMIC_MODE_LABELS[mode])
            action.triggered.connect(
                lambda _checked=False, selected=mode: self.comic_mode_selected.emit(
                    selected
                )
            )
        self.btn_comic_mode.setMenu(self._comic_menu)
        self._reserve_comic_mode_width()
        pill_layout.addWidget(self.btn_comic_mode)

        # Separator
        pill_layout.addWidget(self._make_separator())

        # Zoom controls: -, %, +, Fit
        self.btn_zoom_out = QPushButton("−", self.pill)
        self.btn_zoom_out.setToolTip("Zoom Out (Ctrl+-)")
        self.btn_zoom_out.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom_out.clicked.connect(self.zoom_out_clicked.emit)
        pill_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_label = QPushButton("Window", self.pill)
        self.btn_zoom_label.setToolTip(
            "Switch between Fit Window and Fit Width / Original Size"
        )
        self.btn_zoom_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom_label.clicked.connect(self.zoom_reset_clicked.emit)
        pill_layout.addWidget(self.btn_zoom_label)

        self.btn_zoom_in = QPushButton("+", self.pill)
        self.btn_zoom_in.setToolTip("Zoom In (Ctrl++)")
        self.btn_zoom_in.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom_in.clicked.connect(self.zoom_in_clicked.emit)
        pill_layout.addWidget(self.btn_zoom_in)

        # Separator
        pill_layout.addWidget(self._make_separator())

        # Fullscreen button
        self.btn_fullscreen = QPushButton("⛶", self.pill)
        self.btn_fullscreen.setToolTip("Toggle Fullscreen (F11 or F)")
        self.btn_fullscreen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fullscreen.clicked.connect(self.fullscreen_toggled.emit)
        pill_layout.addWidget(self.btn_fullscreen)

        pill_layout.addWidget(self._make_separator())

        self._hud_size_label = QLabel("HUD: 100%", self.pill)
        self._hud_size_label.setToolTip("HUD and text size")
        pill_layout.addWidget(self._hud_size_label)
        self._hud_size_slider = QSlider(Qt.Orientation.Horizontal, self.pill)
        self._hud_size_slider.setToolTip("Adjust HUD and text size")
        self._hud_size_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hud_size_slider.setRange(75, 150)
        self._hud_size_slider.setSingleStep(5)
        self._hud_size_slider.setPageStep(10)
        self._hud_size_slider.setValue(100)
        self._hud_size_slider.setFixedWidth(110)
        self._hud_size_slider.valueChanged.connect(self._on_hud_scale_changed)
        self._hud_size_slider.sliderPressed.connect(
            self._begin_hud_scale_adjustment
        )
        self._hud_size_slider.sliderReleased.connect(
            self._end_hud_scale_adjustment
        )
        pill_layout.addWidget(self._hud_size_slider)

        pill_layout.addWidget(self._make_separator())

        self.btn_thumbnails = QPushButton("▦", self.pill)
        self.btn_thumbnails.setObjectName("thumbnailToggle")
        self.btn_thumbnails.setCheckable(True)
        self.btn_thumbnails.setChecked(False)
        self.btn_thumbnails.setToolTip("Show or hide page thumbnails")
        self.btn_thumbnails.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_thumbnails.toggled.connect(self._on_thumbnails_toggled)
        pill_layout.addWidget(self.btn_thumbnails)

        thumbnail_parent = self.parentWidget() or self
        self.thumbnail_list = ThumbnailListWidget(thumbnail_parent)
        self.thumbnail_list.setObjectName("thumbnailStrip")
        self.thumbnail_list.setViewMode(QListView.ViewMode.IconMode)
        self.thumbnail_list.setWrapping(False)
        self.thumbnail_list.setMovement(QListView.Movement.Static)
        self.thumbnail_list.setResizeMode(QListView.ResizeMode.Fixed)
        self.thumbnail_list.setUniformItemSizes(True)
        self.thumbnail_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.thumbnail_list.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.thumbnail_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.thumbnail_list.setIconSize(self.THUMBNAIL_ICON_SIZE)
        self.thumbnail_list.setGridSize(self.THUMBNAIL_GRID_SIZE)
        self.thumbnail_list.setStyleSheet(
            "QListWidget#thumbnailStrip {"
            "  background-color: #242830;"
            "  border: none;"
            "  border-radius: 4px;"
            "  outline: none;"
            "}"
            "QListWidget#thumbnailStrip::item {"
            "  background-color: #343944;"
            "  border: 1px solid #464c58;"
            "  border-radius: 3px;"
            "}"
            "QListWidget#thumbnailStrip::item:hover { border-color: #8ab4f8; }"
            "QListWidget#thumbnailStrip::item:selected {"
            "  background-color: #263b58;"
            "  border: 2px solid #8ab4f8;"
            "}"
            "QScrollBar:horizontal { height: 3px; background: transparent; }"
            "QScrollBar::handle:horizontal {"
            "  background: #697180; min-width: 20px; border-radius: 1px;"
            "}"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {"
            "  width: 0px;"
            "}"
            "QScrollBar:vertical { width: 5px; background: transparent; }"
            "QScrollBar::handle:vertical {"
            "  background: #697180; min-height: 24px; border-radius: 2px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "  height: 0px;"
            "}"
        )
        self.thumbnail_list.itemClicked.connect(self._on_thumbnail_clicked)
        self.thumbnail_list.horizontalScrollBar().valueChanged.connect(
            lambda _value: self._queue_visible_thumbnails()
        )
        self.thumbnail_list.verticalScrollBar().valueChanged.connect(
            lambda _value: self._queue_visible_thumbnails()
        )
        self.thumbnail_list.pointer_entered.connect(self._on_thumbnail_entered)
        self.thumbnail_list.pointer_left.connect(self._on_thumbnail_left)
        self._configure_thumbnail_list()
        self.thumbnail_list.hide()

        main_layout.addWidget(self.pill)
        self._apply_hud_scale()
        self.adjustSize()

    def _make_separator(self) -> QWidget:
        sep = QFrame(self.pill)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 0.2); max-width: 1px; margin: 4px 2px;")
        return sep

    def set_page_info(
        self,
        current_index: int,
        total_pages: int,
        can_prev: Optional[bool] = None,
        can_next: Optional[bool] = None,
        display_label: Optional[str] = None,
    ):
        """Update page indicator button and enable/disable navigation buttons."""
        self._display_total_pages = max(0, total_pages)
        if total_pages <= 0:
            self.btn_page.setText("Page 0 / 0")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self._reserve_page_width(0)
            return

        if display_label is not None:
            self.btn_page.setText(display_label)
        else:
            display_idx = current_index + 1 if current_index >= 0 else 1
            self.btn_page.setText(f"Page {display_idx} / {total_pages}")

        self.btn_prev.setEnabled(
            can_prev if can_prev is not None else current_index > 0
        )
        self.btn_next.setEnabled(
            can_next if can_next is not None else current_index < total_pages - 1
        )
        self._reserve_page_width(total_pages)
        self._select_current_thumbnail(current_index)

    def set_page_count(self, total_pages: int) -> None:
        """Reset the per-document thumbnail strip without decoding any pages."""
        self._page_count = max(0, total_pages)
        self._current_thumbnail_index = -1
        self._thumbnail_items_populated = False
        self._thumbnail_requested_indices.clear()
        self._thumbnail_pixmaps.clear()
        self._thumbnail_source_images.clear()
        self.thumbnail_list.clear()
        if self.btn_thumbnails.isChecked():
            self._populate_thumbnail_items()

    def set_thumbnail(self, index: int, image: QImage) -> None:
        """Install a decoded thumbnail and retain it for this document."""
        if not (0 <= index < self._page_count) or image.isNull():
            return

        self._thumbnail_source_images[index] = image.copy()
        self._render_thumbnail(index)

    def page_preview(self, index: int) -> Optional[QPixmap]:
        """Return the decoded page pixels behind a sidebar thumbnail."""
        image = self._thumbnail_source_images.get(index)
        if image is None or image.isNull():
            return None
        return QPixmap.fromImage(image)

    def _render_thumbnail(self, index: int) -> None:
        image = self._thumbnail_source_images.get(index)
        if image is None or image.isNull():
            return
        canvas = QPixmap(self._thumbnail_render_size)
        canvas.fill(QColor("#343944"))
        page_image = image.scaled(
            self._thumbnail_render_size - QSize(4, 4),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        page = QPixmap.fromImage(page_image)
        painter = QPainter(canvas)
        painter.drawPixmap(
            (canvas.width() - page.width()) // 2,
            (canvas.height() - page.height()) // 2,
            page,
        )
        painter.end()

        self._thumbnail_pixmaps[index] = canvas
        if self._thumbnail_items_populated:
            item = self.thumbnail_list.item(index)
            if item is not None:
                item.setIcon(QIcon(canvas))

    def invalidate_thumbnail(self, index: int) -> None:
        """Discard one transformed preview so it can be requested again."""
        if not (0 <= index < self._page_count):
            return
        self._thumbnail_requested_indices.discard(index)
        self._thumbnail_pixmaps.pop(index, None)
        self._thumbnail_source_images.pop(index, None)
        if self._thumbnail_items_populated:
            item = self.thumbnail_list.item(index)
            if item is not None:
                placeholder = QPixmap(self._thumbnail_render_size)
                placeholder.fill(QColor("#343944"))
                item.setIcon(QIcon(placeholder))
        if self.btn_thumbnails.isChecked():
            self._thumbnail_requested_indices.add(index)
            self.thumbnail_requested.emit(index)

    def set_thumbnails_visible(self, visible: bool) -> None:
        """Synchronize the thumbnail strip with a menu or restored setting."""
        previous = self.btn_thumbnails.blockSignals(True)
        self.btn_thumbnails.setChecked(visible)
        self.btn_thumbnails.blockSignals(previous)
        self._apply_thumbnails_visible(visible)

    def thumbnails_visible(self) -> bool:
        return self.btn_thumbnails.isChecked()

    def set_thumbnail_layout(self, layout: str) -> None:
        """Use a horizontal filmstrip or a full-height vertical sidebar."""
        if layout not in {"horizontal", "vertical"}:
            layout = "vertical"
        self._thumbnail_layout = layout
        self._configure_thumbnail_list()
        parent = self.parentWidget()
        if parent is not None:
            self.reposition(parent.width(), parent.height())
        if self.btn_thumbnails.isChecked():
            self._select_current_thumbnail(self._current_thumbnail_index, force=True)

    def thumbnail_layout(self) -> str:
        return self._thumbnail_layout

    def set_hud_scale(self, percent: int) -> None:
        percent = max(75, min(150, int(percent)))
        previous = self._hud_size_slider.blockSignals(True)
        self._hud_size_slider.setValue(percent)
        self._hud_size_slider.blockSignals(previous)
        self._hud_scale_percent = percent
        parent = self.parentWidget()
        if parent is None:
            self._effective_hud_scale_percent = percent
            self._apply_hud_scale()
        else:
            self.reposition(parent.width(), parent.height())

    def hud_scale(self) -> int:
        return self._hud_scale_percent

    def effective_hud_scale(self) -> int:
        """Return the scale currently rendered after fitting the window width."""
        return self._effective_hud_scale_percent

    def _on_hud_scale_changed(self, percent: int) -> None:
        slider_anchor = None
        if self._is_adjusting_hud_scale:
            slider_anchor = self._hud_size_slider.mapToGlobal(QPoint(0, 0))
        self._hud_scale_percent = percent
        parent = self.parentWidget()
        if parent is None:
            self._effective_hud_scale_percent = percent
            self._apply_hud_scale()
        else:
            self._fit_hud_to_width(parent.width())
        if slider_anchor is not None:
            current_anchor = self._hud_size_slider.mapToGlobal(QPoint(0, 0))
            offset = slider_anchor - current_anchor
            self.move(self.x() + offset.x(), self.y() + offset.y())
        elif parent is not None:
            self.reposition(parent.width(), parent.height())
        self.hud_scale_changed.emit(percent)

    def _begin_hud_scale_adjustment(self) -> None:
        """Keep the HUD visible while its inline size slider is dragged."""
        self._is_adjusting_hud_scale = True
        self._hide_timer.stop()

    def _end_hud_scale_adjustment(self) -> None:
        self._is_adjusting_hud_scale = False
        parent = self.parentWidget()
        if parent is not None:
            self.reposition(parent.width(), parent.height())
        if (
            not self._is_mouse_inside
            and not self._is_pointer_in_activation_band
            and not self._is_pointer_in_thumbnail_band
        ):
            self._hide_timer.start()

    def _apply_hud_scale(self) -> None:
        scale = self._effective_hud_scale_percent / 100.0
        font_size = max(8, int(round(13 * scale)))
        vertical_padding = max(2, int(round(4 * scale)))
        horizontal_padding = max(5, int(round(8 * scale)))
        minimum_height = max(20, int(round(24 * scale)))
        radius = max(4, int(round(8 * scale)))
        self.pill.setStyleSheet(
            "#hudPill {"
            "  background-color: rgba(26, 26, 26, 0.90);"
            "  border: 1px solid rgba(255, 255, 255, 0.15);"
            f"  border-radius: {radius}px;"
            "}"
            "QPushButton, QToolButton {"
            "  background: transparent;"
            "  color: #e0e0e0;"
            f"  font-size: {font_size}px;"
            "  font-weight: 500;"
            "  border: none;"
            "  border-radius: 4px;"
            f"  padding: {vertical_padding}px {horizontal_padding}px;"
            f"  min-height: {minimum_height}px;"
            "}"
            "QPushButton:hover, QToolButton:hover {"
            "  background-color: rgba(255, 255, 255, 0.15);"
            "  color: #ffffff;"
            "}"
            "QPushButton:pressed, QToolButton:pressed {"
            "  background-color: rgba(255, 255, 255, 0.25);"
            "}"
            "QPushButton#thumbnailToggle:checked {"
            "  background-color: rgba(74, 144, 226, 0.18);"
            "  border: 2px solid #4a90e2;"
            "}"
            "QPushButton:disabled, QToolButton:disabled { color: #555555; }"
            f"QLabel {{ color: #888888; font-size: {font_size}px; }}"
            "QSlider::groove:horizontal {"
            "  height: 4px; background: #555b66; border-radius: 2px;"
            "}"
            "QSlider::sub-page:horizontal {"
            "  background: #8ab4f8; border-radius: 2px;"
            "}"
            "QSlider::handle:horizontal {"
            "  width: 12px; margin: -4px 0; background: #e0e0e0;"
            "  border: 1px solid #8ab4f8; border-radius: 6px;"
            "}"
        )
        pill_layout = self.pill.layout()
        if pill_layout is not None:
            pill_layout.setContentsMargins(
                max(6, int(round(10 * scale))),
                max(3, int(round(5 * scale))),
                max(6, int(round(10 * scale))),
                max(3, int(round(5 * scale))),
            )
            pill_layout.setSpacing(max(3, int(round(6 * scale))))
        self.btn_page.setStyleSheet(
            "font-weight: bold; "
            f"padding: {vertical_padding}px {max(7, int(round(10 * scale)))}px; "
            "color: #ffffff;"
        )
        self._hud_size_label.setText(f"HUD: {self._hud_scale_percent}%")
        self._hud_size_slider.setFixedWidth(max(64, int(round(110 * scale))))
        self._refresh_layout_geometry()

    def _fit_hud_to_width(self, parent_width: int) -> None:
        """Shrink the rendered HUD as needed while retaining the chosen scale."""
        available_width = max(1, parent_width - (2 * self.EDGE_MARGIN))
        candidate = self._hud_scale_percent
        self._effective_hud_scale_percent = candidate
        self._apply_hud_scale()

        # Font metrics and per-widget padding round independently, so allow a
        # few convergence passes rather than trusting one proportional step.
        for _attempt in range(8):
            current_width = self.sizeHint().width()
            if current_width <= available_width:
                break
            fitted = int(candidate * available_width / max(1, current_width))
            candidate = max(
                self.MIN_RESPONSIVE_SCALE_PERCENT,
                min(candidate - 1, fitted),
            )
            self._effective_hud_scale_percent = candidate
            self._apply_hud_scale()
            if candidate == self.MIN_RESPONSIVE_SCALE_PERCENT:
                break

    def set_at_top(self, at_top: bool) -> None:
        self._at_top = bool(at_top)
        parent = self.parentWidget()
        if parent is not None:
            self.reposition(parent.width(), parent.height())

    def is_at_top(self) -> bool:
        return self._at_top

    def _on_thumbnails_toggled(self, visible: bool) -> None:
        self._apply_thumbnails_visible(visible)
        self.thumbnails_toggled.emit(visible)

    def _apply_thumbnails_visible(self, visible: bool) -> None:
        if visible:
            self._populate_thumbnail_items()
            if not self.isHidden() or self._fade_target_visible:
                self._show_thumbnail_panel()
            self._select_current_thumbnail(self._current_thumbnail_index, force=True)
            QTimer.singleShot(0, self._queue_visible_thumbnails)
        else:
            self.thumbnail_list.hide()
        self._refresh_layout_geometry()
        parent = self.parentWidget()
        if parent is not None:
            self.reposition(parent.width(), parent.height())

    def _populate_thumbnail_items(self) -> None:
        if self._thumbnail_items_populated:
            return
        self.thumbnail_list.clear()
        placeholder = QPixmap(self._thumbnail_render_size)
        placeholder.fill(QColor("#343944"))
        placeholder_icon = QIcon(placeholder)
        for index in range(self._page_count):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(f"Go to page {index + 1}")
            item.setSizeHint(self._thumbnail_grid_size)
            item.setIcon(
                QIcon(self._thumbnail_pixmaps[index])
                if index in self._thumbnail_pixmaps
                else placeholder_icon
            )
            self.thumbnail_list.addItem(item)
        self._thumbnail_items_populated = True

    def _configure_thumbnail_list(self) -> None:
        is_vertical = self._thumbnail_layout == "vertical"
        self.thumbnail_list.setFlow(
            QListView.Flow.TopToBottom
            if is_vertical
            else QListView.Flow.LeftToRight
        )
        self.thumbnail_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            if is_vertical
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.thumbnail_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if is_vertical
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.thumbnail_list.scheduleDelayedItemsLayout()

    def _select_current_thumbnail(self, index: int, force: bool = False) -> None:
        if not (0 <= index < self._page_count):
            return
        changed = index != self._current_thumbnail_index
        self._current_thumbnail_index = index
        if not self.btn_thumbnails.isChecked():
            return
        self._populate_thumbnail_items()
        item = self.thumbnail_list.item(index)
        if item is None:
            return
        self.thumbnail_list.setCurrentItem(item)
        if changed or force:
            self.thumbnail_list.scrollToItem(
                item, QAbstractItemView.ScrollHint.PositionAtCenter
            )
            QTimer.singleShot(0, self._queue_visible_thumbnails)

    def _queue_visible_thumbnails(self) -> None:
        if not self.btn_thumbnails.isChecked() or self._page_count <= 0:
            return
        is_vertical = self._thumbnail_layout == "vertical"
        item_extent = max(
            1,
            self._thumbnail_grid_size.height()
            if is_vertical
            else self._thumbnail_grid_size.width(),
        )
        viewport_extent = max(
            item_extent,
            self.thumbnail_list.viewport().height()
            if is_vertical
            else self.thumbnail_list.viewport().width(),
        )
        scrollbar = (
            self.thumbnail_list.verticalScrollBar()
            if is_vertical
            else self.thumbnail_list.horizontalScrollBar()
        )
        first = max(0, scrollbar.value() // item_extent - 2)
        visible_count = viewport_extent // item_extent + 5
        indices = set(range(first, min(self._page_count, first + visible_count)))
        if 0 <= self._current_thumbnail_index < self._page_count:
            indices.update(
                range(
                    max(0, self._current_thumbnail_index - 2),
                    min(self._page_count, self._current_thumbnail_index + 3),
                )
            )
        ordered = sorted(
            indices,
            key=lambda value: (abs(value - self._current_thumbnail_index), value),
        )
        for index in ordered:
            if index in self._thumbnail_requested_indices:
                continue
            self._thumbnail_requested_indices.add(index)
            self.thumbnail_requested.emit(index)

    def _on_thumbnail_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int):
            self.thumbnail_clicked.emit(index)

    def _on_thumbnail_entered(self) -> None:
        self._is_mouse_inside = True
        self._hide_timer.stop()
        self._show_with_fade()

    def _on_thumbnail_left(self) -> None:
        self._is_mouse_inside = False
        if not self.isHidden():
            self._hide_timer.start()

    def _show_thumbnail_panel(self) -> None:
        if not self.btn_thumbnails.isChecked() or self._page_count <= 0:
            return
        self.thumbnail_list.show()
        self.thumbnail_list.raise_()

    def _reserve_page_width(self, total_pages: int) -> None:
        """Keep both the maximum count and current range label readable."""
        widest_text = f"Page {total_pages} / {total_pages}"
        metrics = self.btn_page.fontMetrics()
        text_width = max(
            metrics.horizontalAdvance(widest_text),
            metrics.horizontalAdvance(self.btn_page.text()),
        )
        scale = self._effective_hud_scale_percent / 100.0
        horizontal_padding = max(7, int(round(10 * scale)))
        self.btn_page.setMinimumWidth(text_width + (2 * horizontal_padding) + 4)
        self.adjustSize()

    def set_mode(self, is_scroll: bool):
        """Update mode switcher button label."""
        if is_scroll:
            self.btn_mode.setText("📜 Scroll")
        else:
            self.btn_mode.setText("📄 Single")

    def set_zoom(self, zoom_factor: float, mode: str = "custom"):
        """Show the active fit behavior, using percentages only for manual zoom."""
        fit_labels = {
            "window": "Window",
            "width": "Width",
            "original": "Original",
        }
        label = fit_labels.get(mode)
        if label is None:
            label = f"{int(round(zoom_factor * 100))}%"
        self.btn_zoom_label.setText(label)

    def set_fullscreen(self, is_fullscreen: bool):
        """Update fullscreen button tooltip and symbol."""
        if is_fullscreen:
            self.btn_fullscreen.setText("🗗")
            self.btn_fullscreen.setToolTip("Exit Fullscreen (F11, F, or Esc)")
        else:
            self.btn_fullscreen.setText("⛶")
            self.btn_fullscreen.setToolTip("Enter Fullscreen (F11 or F)")

    def set_comic_mode(self, mode: str) -> None:
        self.btn_comic_mode.setText(
            self.COMIC_MODE_LABELS.get(mode, self.COMIC_MODE_LABELS["custom"])
        )
        self._refresh_layout_geometry()

    def _reserve_comic_mode_width(self) -> None:
        """Keep the selector and its popup stable at the widest choice width."""
        metrics = self.btn_comic_mode.fontMetrics()
        widest_label = max(
            metrics.horizontalAdvance(label)
            for label in self.COMIC_MODE_LABELS.values()
        )
        # Space for the HUD padding and QToolButton's menu indicator. The popup
        # uses the same fixed width so it aligns with the selector instead of
        # changing width with the active choice.
        selector_width = widest_label + 48
        self.btn_comic_mode.setFixedWidth(selector_width)
        self._comic_menu.setFixedWidth(selector_width)

    def _reserve_zoom_label_width(self) -> None:
        """Prevent fit-mode names and custom percentages from shifting the HUD."""
        metrics = self.btn_zoom_label.fontMetrics()
        widest_label = max(
            metrics.horizontalAdvance(label)
            for label in ("Window", "Width", "Original", "5000%")
        )
        self.btn_zoom_label.setFixedWidth(widest_label + 24)

    def _refresh_layout_geometry(self) -> None:
        """Polish and activate the initial HUD layout before it is displayed."""
        self.ensurePolished()
        self.pill.ensurePolished()
        self._reserve_page_width(self._display_total_pages)
        self._reserve_comic_mode_width()
        self._reserve_zoom_label_width()
        for layout in (self.pill.layout(), self.layout()):
            if layout is not None:
                layout.invalidate()
                layout.activate()
        self.adjustSize()

    def reposition(self, parent_width: int, parent_height: int):
        """Center the HUD horizontally near the configured viewer edge."""
        self._fit_hud_to_width(parent_width)
        w = self.sizeHint().width()
        h = self.sizeHint().height()
        x = max(0, (parent_width - w) // 2)
        menu_offset = 0
        parent = self.parentWidget()
        menu_bar = getattr(parent, "menuBar", lambda: None)()
        if menu_bar is not None and menu_bar.isVisible():
            menu_offset = menu_bar.height()
        if self._at_top:
            y = menu_offset + self.EDGE_MARGIN
        else:
            y = parent_height - h - self.EDGE_MARGIN
        self.setGeometry(x, max(0, y), w, h)
        self._reposition_thumbnail_panel(parent_width, parent_height, menu_offset)

    def _reposition_thumbnail_panel(
        self, parent_width: int, parent_height: int, menu_offset: int
    ) -> None:
        if self._thumbnail_layout == "vertical":
            top = menu_offset + 12
            height = max(120, parent_height - top - 12)
            self.thumbnail_list.setGeometry(
                12,
                top,
                min(self.THUMBNAIL_SIDEBAR_WIDTH, max(120, parent_width - 24)),
                height,
            )
            self._update_thumbnail_dimensions()
            return

        width = min(self.THUMBNAIL_STRIP_WIDTH, max(180, parent_width - 32))
        height = min(
            self.THUMBNAIL_FILMSTRIP_HEIGHT,
            max(120, parent_height - menu_offset - self.height() - 48),
        )
        x = max(0, (parent_width - width) // 2)
        if self._at_top:
            y = self.y() + self.height() + 8
        else:
            y = self.y() - height - 8
        y = max(menu_offset + 8, min(y, parent_height - height - 8))
        self.thumbnail_list.setGeometry(x, y, width, height)
        self._update_thumbnail_dimensions()

    def _update_thumbnail_dimensions(self) -> None:
        """Fit exactly five sidebar slots or six filmstrip slots without cropping."""
        if self._thumbnail_layout == "vertical":
            grid_size = QSize(
                max(20, self.thumbnail_list.width() - 14),
                max(20, (self.thumbnail_list.height() - 4) // self.VERTICAL_VISIBLE_COUNT),
            )
        else:
            grid_size = QSize(
                max(20, (self.thumbnail_list.width() - 4) // self.HORIZONTAL_VISIBLE_COUNT),
                max(20, self.thumbnail_list.height() - 8),
            )
        render_size = QSize(
            max(8, grid_size.width() - 12),
            max(8, grid_size.height() - 12),
        )
        if (
            grid_size == self._thumbnail_grid_size
            and render_size == self._thumbnail_render_size
        ):
            return
        self._thumbnail_grid_size = grid_size
        self._thumbnail_render_size = render_size
        self.thumbnail_list.setGridSize(grid_size)
        self.thumbnail_list.setIconSize(render_size)
        for index in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(index)
            if item is not None:
                item.setSizeHint(grid_size)
        for index in tuple(self._thumbnail_source_images):
            self._render_thumbnail(index)

    def on_pointer_move(self, parent_y: int, parent_x: Optional[int] = None) -> None:
        """Reveal controls from the HUD edge or the enabled thumbnail edge."""
        band_top = self.y() - self.ACTIVATION_MARGIN
        band_bottom = self.y() + self.height() + self.ACTIVATION_MARGIN
        is_in_band = band_top <= parent_y <= band_bottom
        is_in_thumbnail_band = False
        if parent_x is not None and self.btn_thumbnails.isChecked():
            panel = self.thumbnail_list.geometry()
            if self._thumbnail_layout == "vertical":
                is_in_thumbnail_band = (
                    -self.ACTIVATION_MARGIN
                    <= parent_x
                    <= panel.right() + self.ACTIVATION_MARGIN
                    and panel.top() - self.ACTIVATION_MARGIN
                    <= parent_y
                    <= panel.bottom() + self.ACTIVATION_MARGIN
                )
            else:
                is_in_thumbnail_band = panel.adjusted(
                    -self.ACTIVATION_MARGIN,
                    -self.ACTIVATION_MARGIN,
                    self.ACTIVATION_MARGIN,
                    self.ACTIVATION_MARGIN,
                ).contains(parent_x, parent_y)
        if (
            is_in_band == self._is_pointer_in_activation_band
            and is_in_thumbnail_band == self._is_pointer_in_thumbnail_band
            and not ((is_in_band or is_in_thumbnail_band) and self.isHidden())
        ):
            return

        self._is_pointer_in_activation_band = is_in_band
        self._is_pointer_in_thumbnail_band = is_in_thumbnail_band
        if is_in_band or is_in_thumbnail_band:
            self._show_with_fade()
        elif not self.isHidden() and not self._is_mouse_inside:
            self._hide_timer.start()

    def toggle_visibility(self) -> None:
        """Toggle the HUD immediately, independent of its hover state."""
        self._hide_timer.stop()
        if not self.isHidden() and self._fade_target_visible:
            self._fade_out()
        else:
            self._show_with_fade()

    def hide_immediately(self) -> None:
        """Reset and hide the HUD without leaving an animation pending."""
        self._hide_timer.stop()
        self._fade_animation.stop()
        self._fade_target_visible = False
        self._opacity_effect.setOpacity(1.0)
        self.thumbnail_list.hide()
        self.hide()

    def toggle_pin(self) -> None:
        """Backwards-compatible name for the HUD visibility shortcut."""
        self.toggle_visibility()

    def enterEvent(self, event):
        self._is_mouse_inside = True
        self._hide_timer.stop()
        self._show_with_fade()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_mouse_inside = False
        if not self.isHidden() and not self._is_adjusting_hud_scale:
            self._hide_timer.start()
        super().leaveEvent(event)

    def _auto_hide(self):
        if (
            not self._is_mouse_inside
            and not self._is_pointer_in_activation_band
            and not self._is_pointer_in_thumbnail_band
            and not self._is_adjusting_hud_scale
        ):
            self._fade_out()

    def _show_with_fade(self) -> None:
        start_opacity = (
            self._opacity_effect.opacity() if not self.isHidden() else 0.0
        )
        self._fade_target_visible = True
        self._fade_animation.stop()
        self._opacity_effect.setOpacity(start_opacity)
        self.show()
        self.raise_()
        self._show_thumbnail_panel()
        self._fade_animation.setStartValue(start_opacity)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()

    def _fade_out(self) -> None:
        self._fade_target_visible = False
        self._fade_animation.stop()
        self._fade_animation.setStartValue(self._opacity_effect.opacity())
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.start()

    def _finish_fade(self) -> None:
        if self._opacity_effect.opacity() <= 0.0:
            self.thumbnail_list.hide()
            self.hide()
            self._opacity_effect.setOpacity(1.0)
            parent = self.parentWidget()
            if parent is not None:
                self.reposition(parent.width(), parent.height())
