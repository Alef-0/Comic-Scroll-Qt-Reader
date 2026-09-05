"""Floating HUD overlay for Qt Scroll Reader."""

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ViewerHud(QWidget):
    """Floating HUD overlay positioned at the bottom of the viewer window.

    Provides quick visual access to page navigation, mode switching, zoom levels,
    and fullscreen toggle, with auto-hiding after inactivity.
    """

    first_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    last_clicked = pyqtSignal()
    jump_clicked = pyqtSignal()
    mode_toggled = pyqtSignal()
    zoom_in_clicked = pyqtSignal()
    zoom_out_clicked = pyqtSignal()
    zoom_reset_clicked = pyqtSignal()
    fullscreen_toggled = pyqtSignal()

    HIDE_DELAY_MS = 3000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._is_pinned = False
        self._is_mouse_inside = False

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
            "QPushButton {"
            "  background: transparent;"
            "  color: #e0e0e0;"
            "  font-size: 13px;"
            "  font-weight: 500;"
            "  border: none;"
            "  border-radius: 4px;"
            "  padding: 4px 8px;"
            "  min-height: 24px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(255, 255, 255, 0.15);"
            "  color: #ffffff;"
            "}"
            "QPushButton:pressed {"
            "  background-color: rgba(255, 255, 255, 0.25);"
            "}"
            "QPushButton:disabled {"
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

        # Navigation: First, Prev
        self.btn_first = QPushButton("⏮", self.pill)
        self.btn_first.setToolTip("First page (Home)")
        self.btn_first.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_first.clicked.connect(self.first_clicked.emit)
        pill_layout.addWidget(self.btn_first)

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

        # Navigation: Next, Last
        self.btn_next = QPushButton("▶", self.pill)
        self.btn_next.setToolTip("Next page (Right/Down/Space)")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.clicked.connect(self.next_clicked.emit)
        pill_layout.addWidget(self.btn_next)

        self.btn_last = QPushButton("⏭", self.pill)
        self.btn_last.setToolTip("Last page (End)")
        self.btn_last.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_last.clicked.connect(self.last_clicked.emit)
        pill_layout.addWidget(self.btn_last)

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
            self.btn_first.setEnabled(False)
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.btn_last.setEnabled(False)
            return

        display_idx = current_index + 1 if current_index >= 0 else 1
        self.btn_page.setText(f"Page {display_idx} / {total_pages}")
        self.btn_first.setEnabled(current_index > 0)
        self.btn_prev.setEnabled(current_index > 0)
        self.btn_next.setEnabled(current_index < total_pages - 1)
        self.btn_last.setEnabled(current_index < total_pages - 1)

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

    def reposition(self, parent_width: int, parent_height: int):
        """Center the HUD horizontally near the bottom of the parent window."""
        self.adjustSize()
        w = self.sizeHint().width()
        h = self.sizeHint().height()
        x = (parent_width - w) // 2
        y = parent_height - h - 24  # 24px margin from bottom
        self.setGeometry(x, max(0, y), w, h)

    def on_user_interaction(self):
        """Call when user moves mouse or interacts to show HUD and restart hide timer."""
        if not self._is_pinned:
            if not self.isVisible():
                self.show()
            self._hide_timer.start()

    def toggle_pin(self):
        """Toggle pinned state (always visible vs auto-hide)."""
        self._is_pinned = not self._is_pinned
        if self._is_pinned:
            self._hide_timer.stop()
            self.show()
        else:
            self._hide_timer.start()

    def enterEvent(self, event):
        self._is_mouse_inside = True
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_mouse_inside = False
        if not self._is_pinned and self.isVisible():
            self._hide_timer.start()
        super().leaveEvent(event)

    def _auto_hide(self):
        if not self._is_pinned and not self._is_mouse_inside:
            self.hide()
