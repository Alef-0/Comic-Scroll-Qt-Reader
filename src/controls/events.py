"""Mouse and keyboard event handlers for the image viewer."""

from typing import Callable, Optional
from PyQt6.QtCore import QObject, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent


class CommonViewerControls(QObject):
    """Common control handler for viewer widgets, creating signals that activate viewer functions."""

    pan_requested = pyqtSignal(float, float)
    zoom_anchor_requested = pyqtSignal(float, QPointF)
    zoom_in_requested = pyqtSignal()
    zoom_out_requested = pyqtSignal()
    reset_view_requested = pyqtSignal()
    next_image_requested = pyqtSignal()
    prev_image_requested = pyqtSignal()
    first_image_requested = pyqtSignal()
    last_image_requested = pyqtSignal()
    toggle_mode_requested = pyqtSignal()
    mode_single_requested = pyqtSignal()
    mode_scroll_requested = pyqtSignal()
    cursor_change_requested = pyqtSignal(object)

    WHEEL_THRESHOLD = 120

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._is_dragging: bool = False
        self._last_mouse_pos: QPointF = QPointF(0, 0)
        self._wheel_accumulator: int = 0

    @property
    def is_dragging(self) -> bool:
        return self._is_dragging

    def connect_viewer(self, viewer) -> None:
        """Connect common control signals directly to viewer functions and signals."""
        if hasattr(viewer, "pan_by"):
            self.pan_requested.connect(viewer.pan_by)
        if hasattr(viewer, "zoom_at"):
            self.zoom_anchor_requested.connect(viewer.zoom_at)
        if hasattr(viewer, "zoom_in"):
            self.zoom_in_requested.connect(viewer.zoom_in)
        if hasattr(viewer, "zoom_out"):
            self.zoom_out_requested.connect(viewer.zoom_out)

        if hasattr(viewer, "reset_view"):
            self.reset_view_requested.connect(viewer.reset_view)
        elif hasattr(viewer, "reset_zoom"):
            self.reset_view_requested.connect(viewer.reset_zoom)

        if hasattr(viewer, "setCursor"):
            self.cursor_change_requested.connect(viewer.setCursor)

        if hasattr(viewer, "toggle_mode_requested"):
            self.toggle_mode_requested.connect(viewer.toggle_mode_requested.emit)
        if hasattr(viewer, "mode_single_requested"):
            self.mode_single_requested.connect(viewer.mode_single_requested.emit)
        if hasattr(viewer, "mode_scroll_requested"):
            self.mode_scroll_requested.connect(viewer.mode_scroll_requested.emit)

        if hasattr(viewer, "next_image_requested"):
            self.next_image_requested.connect(viewer.next_image_requested.emit)
        if hasattr(viewer, "prev_image_requested"):
            self.prev_image_requested.connect(viewer.prev_image_requested.emit)

    def handle_mouse_press(self, event: QMouseEvent) -> bool:
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._last_mouse_pos = event.position()
            self.cursor_change_requested.emit(Qt.CursorShape.ClosedHandCursor)
            return True
        elif button == Qt.MouseButton.RightButton:
            self.toggle_mode_requested.emit()
            return True
        elif button == Qt.MouseButton.MiddleButton:
            self.next_image_requested.emit()
            return True
        elif button == Qt.MouseButton.ForwardButton:
            self.next_image_requested.emit()
            return True
        elif button == Qt.MouseButton.BackButton:
            self.prev_image_requested.emit()
            return True
        return False

    def handle_mouse_move(self, event: QMouseEvent) -> bool:
        if self._is_dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            cur_pos = event.position()
            delta = cur_pos - self._last_mouse_pos
            self._last_mouse_pos = cur_pos
            self.pan_requested.emit(delta.x(), delta.y())
            return True
        return False

    def handle_mouse_release(self, event: QMouseEvent, is_zoomed: bool = False) -> bool:
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            cursor = (
                Qt.CursorShape.OpenHandCursor
                if is_zoomed
                else Qt.CursorShape.ArrowCursor
            )
            self.cursor_change_requested.emit(cursor)
            return True
        return False

    def handle_double_click(self, event: QMouseEvent) -> bool:
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view_requested.emit()
            return True
        return False

    def handle_wheel(self, event: QWheelEvent, handle_navigation: bool = True) -> bool:
        modifiers = event.modifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        delta_y = event.angleDelta().y()

        if delta_y == 0:
            return False

        if is_ctrl:
            scale_factor = 1.25 ** (delta_y / 120.0)
            self.zoom_anchor_requested.emit(scale_factor, event.position())
            return True
        elif handle_navigation:
            self._wheel_accumulator += delta_y
            if abs(self._wheel_accumulator) >= self.WHEEL_THRESHOLD:
                if self._wheel_accumulator < 0:
                    self.next_image_requested.emit()
                else:
                    self.prev_image_requested.emit()
                self._wheel_accumulator = 0
            return True
        return False

    def handle_key_press(self, event: QKeyEvent) -> bool:
        modifiers = event.modifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        key = event.key()

        if is_ctrl:
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.zoom_in_requested.emit()
                return True
            elif key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
                self.zoom_out_requested.emit()
                return True
            elif key in (Qt.Key.Key_0, Qt.Key.Key_ParenRight):
                self.reset_view_requested.emit()
                return True
        else:
            if key == Qt.Key.Key_1:
                self.mode_single_requested.emit()
                self.toggle_mode_requested.emit()
                return True
            elif key == Qt.Key.Key_2:
                self.mode_scroll_requested.emit()
                self.toggle_mode_requested.emit()
                return True
            elif key in (
                Qt.Key.Key_Right,
                Qt.Key.Key_Down,
                Qt.Key.Key_PageDown,
                Qt.Key.Key_Space,
            ):
                self.next_image_requested.emit()
                return True
            elif key in (
                Qt.Key.Key_Left,
                Qt.Key.Key_Up,
                Qt.Key.Key_PageUp,
                Qt.Key.Key_Backspace,
            ):
                self.prev_image_requested.emit()
                return True
            elif key == Qt.Key.Key_Home:
                self.first_image_requested.emit()
                return True
            elif key in (Qt.Key.Key_End,):
                self.last_image_requested.emit()
                return True

        return False


class KeyboardEventHandler:
    """Handles keyboard inputs for image navigation and zoom control."""

    def __init__(
        self,
        on_next_image: Optional[Callable[[], None]] = None,
        on_prev_image: Optional[Callable[[], None]] = None,
        on_first_image: Optional[Callable[[], None]] = None,
        on_last_image: Optional[Callable[[], None]] = None,
        on_zoom_in: Optional[Callable[[], None]] = None,
        on_zoom_out: Optional[Callable[[], None]] = None,
        on_reset_zoom: Optional[Callable[[], None]] = None,
        on_mode_single: Optional[Callable[[], None]] = None,
        on_mode_scroll: Optional[Callable[[], None]] = None,
        on_toggle_mode: Optional[Callable[[], None]] = None,
    ):
        self.on_next_image = on_next_image
        self.on_prev_image = on_prev_image
        self.on_first_image = on_first_image
        self.on_last_image = on_last_image
        self.on_zoom_in = on_zoom_in
        self.on_zoom_out = on_zoom_out
        self.on_reset_zoom = on_reset_zoom
        self.on_mode_single = on_mode_single
        self.on_mode_scroll = on_mode_scroll
        self.on_toggle_mode = on_toggle_mode

    def handle_key_press(self, event: QKeyEvent) -> bool:
        """Process key press event. Returns True if handled, False otherwise."""
        modifiers = event.modifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        key = event.key()

        # Zoom keys (with Ctrl)
        if is_ctrl:
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                if self.on_zoom_in:
                    self.on_zoom_in()
                return True
            elif key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
                if self.on_zoom_out:
                    self.on_zoom_out()
                return True
            elif key in (Qt.Key.Key_0, Qt.Key.Key_ParenRight):
                if self.on_reset_zoom:
                    self.on_reset_zoom()
                return True

        # Navigation keys (without Ctrl)
        else:
            if key in (
                Qt.Key.Key_Right,
                Qt.Key.Key_Down,
                Qt.Key.Key_PageDown,
                Qt.Key.Key_Space,
            ):
                if self.on_next_image:
                    self.on_next_image()
                return True
            elif key in (
                Qt.Key.Key_Left,
                Qt.Key.Key_Up,
                Qt.Key.Key_PageUp,
                Qt.Key.Key_Backspace,
            ):
                if self.on_prev_image:
                    self.on_prev_image()
                return True
            elif key == Qt.Key.Key_Home:
                if self.on_first_image:
                    self.on_first_image()
                return True
            elif key in (Qt.Key.Key_End,):
                if self.on_last_image:
                    self.on_last_image()
                return True
            elif key == Qt.Key.Key_1:
                if self.on_mode_single:
                    self.on_mode_single()
                    return True
                elif self.on_toggle_mode:
                    self.on_toggle_mode()
                    return True
            elif key == Qt.Key.Key_2:
                if self.on_mode_scroll:
                    self.on_mode_scroll()
                    return True
                elif self.on_toggle_mode:
                    self.on_toggle_mode()
                    return True

        return False


class MouseEventHandler:
    """Handles mouse dragging, wheel zoom/navigation, and button clicks."""

    WHEEL_THRESHOLD = 120

    def __init__(
        self,
        on_pan: Optional[Callable[[float, float], None]] = None,
        on_zoom_anchor: Optional[Callable[[float, QPointF], None]] = None,
        on_next_image: Optional[Callable[[], None]] = None,
        on_prev_image: Optional[Callable[[], None]] = None,
        on_reset_view: Optional[Callable[[], None]] = None,
        on_cursor_change: Optional[Callable[[Qt.CursorShape], None]] = None,
        on_toggle_mode: Optional[Callable[[], None]] = None,
    ):
        self.on_pan = on_pan
        self.on_zoom_anchor = on_zoom_anchor
        self.on_next_image = on_next_image
        self.on_prev_image = on_prev_image
        self.on_reset_view = on_reset_view
        self.on_cursor_change = on_cursor_change
        self.on_toggle_mode = on_toggle_mode

        self._is_dragging: bool = False
        self._last_mouse_pos: QPointF = QPointF(0, 0)
        self._wheel_accumulator: int = 0

    @property
    def is_dragging(self) -> bool:
        """Return whether dragging is currently in progress."""
        return self._is_dragging

    def handle_mouse_press(self, event: QMouseEvent) -> bool:
        """Handle mouse button press events."""
        button = event.button()

        # Left mouse button starts drag panning
        if button == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._last_mouse_pos = event.position()
            if self.on_cursor_change:
                self.on_cursor_change(Qt.CursorShape.ClosedHandCursor)
            return True

        # Right mouse button alternates/toggles viewer modes
        elif button == Qt.MouseButton.RightButton:
            if self.on_toggle_mode:
                self.on_toggle_mode()
                return True

        # Middle mouse button (wheel press) triggers next image
        elif button == Qt.MouseButton.MiddleButton:
            if self.on_next_image:
                self.on_next_image()
            return True

        # Mouse side buttons for navigation
        elif button == Qt.MouseButton.ForwardButton:
            if self.on_next_image:
                self.on_next_image()
            return True
        elif button == Qt.MouseButton.BackButton:
            if self.on_prev_image:
                self.on_prev_image()
            return True

        return False

    def handle_mouse_move(self, event: QMouseEvent) -> bool:
        """Handle mouse movement for dragging the image."""
        if self._is_dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            current_pos = event.position()
            delta = current_pos - self._last_mouse_pos
            self._last_mouse_pos = current_pos
            if self.on_pan:
                self.on_pan(delta.x(), delta.y())
            return True
        return False

    def handle_mouse_release(self, event: QMouseEvent, is_zoomed: bool = False) -> bool:
        """Handle mouse button release to stop dragging."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            if self.on_cursor_change:
                cursor = (
                    Qt.CursorShape.OpenHandCursor
                    if is_zoomed
                    else Qt.CursorShape.ArrowCursor
                )
                self.on_cursor_change(cursor)
            return True
        return False

    def handle_double_click(self, event: QMouseEvent) -> bool:
        """Double click resets zoom and center position."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.on_reset_view:
                self.on_reset_view()
            return True
        return False

    def handle_wheel(self, event: QWheelEvent) -> bool:
        """Handle mouse wheel for zooming (with Ctrl) or navigation (without Ctrl)."""
        modifiers = event.modifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        delta_y = event.angleDelta().y()

        if delta_y == 0:
            return False

        if is_ctrl:
            # Zoom anchored at mouse position
            scale_factor = 1.25 ** (delta_y / 120.0)
            if self.on_zoom_anchor:
                self.on_zoom_anchor(scale_factor, event.position())
            return True
        else:
            # Scroll wheel navigation
            self._wheel_accumulator += delta_y
            if abs(self._wheel_accumulator) >= self.WHEEL_THRESHOLD:
                if self._wheel_accumulator < 0:
                    if self.on_next_image:
                        self.on_next_image()
                else:
                    if self.on_prev_image:
                        self.on_prev_image()
                self._wheel_accumulator = 0
            return True
