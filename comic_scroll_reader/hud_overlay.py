"""Floating reader-controls HUD for Comic Scroll Reader."""

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
)


class ViewerHud(QWidget):
    """Floating HUD overlay positioned at the bottom of the viewer window.

    Provides quick visual access to page navigation, mode switching, zoom levels,
    and fullscreen toggle, with auto-hiding after inactivity.
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

    HIDE_DELAY_MS = 900
    FADE_DURATION_MS = 350
    ACTIVATION_MARGIN = 28
    COMIC_MODE_LABELS = {
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
        self._fade_target_visible = False

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
            "QPushButton:disabled, QToolButton:disabled {"
            "  color: #555555;"
            "}"
            "QLabel {"
            "  color: #888888;"
            "  font-size: 13px;"
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
        self.btn_next.setToolTip("Next page (Right/Down/Space)")
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
        self.btn_comic_mode.setText(self.COMIC_MODE_LABELS["custom"])
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
        for mode in ("comics", "manga", "webtoon"):
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

        self.btn_zoom_label = QPushButton("100%", self.pill)
        self.btn_zoom_label.setToolTip("Reset Zoom to Fit (Ctrl+0)")
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

        main_layout.addWidget(self.pill)
        self.adjustSize()

    def _make_separator(self) -> QWidget:
        sep = QFrame(self.pill)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 0.2); max-width: 1px; margin: 4px 2px;")
        return sep

    def set_page_info(self, current_index: int, total_pages: int):
        """Update page indicator button and enable/disable navigation buttons."""
        if total_pages <= 0:
            self.btn_page.setText("Page 0 / 0")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self._reserve_page_width(0)
            return

        display_idx = current_index + 1 if current_index >= 0 else 1
        self.btn_page.setText(f"Page {display_idx} / {total_pages}")
        self.btn_prev.setEnabled(current_index > 0)
        self.btn_next.setEnabled(current_index < total_pages - 1)
        self._reserve_page_width(total_pages)

    def _reserve_page_width(self, total_pages: int) -> None:
        """Keep the widest page count readable instead of letting it compress."""
        widest_text = f"Page {total_pages} / {total_pages}"
        text_width = self.btn_page.fontMetrics().horizontalAdvance(widest_text)
        self.btn_page.setMinimumWidth(text_width + 24)
        self.adjustSize()

    def set_mode(self, is_scroll: bool):
        """Update mode switcher button label."""
        if is_scroll:
            self.btn_mode.setText("📜 Scroll")
        else:
            self.btn_mode.setText("📄 Single")

    def set_zoom(self, zoom_factor: float):
        """Update zoom label display."""
        pct = int(round(zoom_factor * 100))
        self.btn_zoom_label.setText(f"{pct}%")

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
        self.adjustSize()

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

    def reposition(self, parent_width: int, parent_height: int):
        """Center the HUD horizontally near the bottom of the parent window."""
        self.adjustSize()
        w = self.sizeHint().width()
        h = self.sizeHint().height()
        x = (parent_width - w) // 2
        y = parent_height - h - 24  # 24px margin from bottom
        self.setGeometry(x, max(0, y), w, h)

    def on_pointer_move(self, parent_y: int) -> None:
        """Reveal the HUD only while the pointer is near its vertical level."""
        band_top = self.y() - self.ACTIVATION_MARGIN
        band_bottom = self.y() + self.height() + self.ACTIVATION_MARGIN
        is_in_band = band_top <= parent_y <= band_bottom
        if (
            is_in_band == self._is_pointer_in_activation_band
            and not (is_in_band and self.isHidden())
        ):
            return

        self._is_pointer_in_activation_band = is_in_band
        if is_in_band:
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
        if not self.isHidden():
            self._hide_timer.start()
        super().leaveEvent(event)

    def _auto_hide(self):
        if (
            not self._is_mouse_inside
            and not self._is_pointer_in_activation_band
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
            self.hide()
            self._opacity_effect.setOpacity(1.0)
