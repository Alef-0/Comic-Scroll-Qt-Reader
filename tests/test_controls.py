"""Unit tests for KeyboardEventHandler and MouseEventHandler."""

import unittest
from PyQt6.QtCore import Qt, QPointF, QPoint
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication

from src.controls.events import (
    CommonViewerControls,
    KeyboardEventHandler,
    MouseEventHandler,
)

# Ensure QApplication is initialized for QKeyEvent / QMouseEvent / QWheelEvent
app = QApplication.instance()
if app is None:
    app = QApplication(["--platform", "offscreen"])


class TestKeyboardEventHandler(unittest.TestCase):
    """Test suite for KeyboardEventHandler."""

    def setUp(self):
        self.events_called = []
        self.handler = KeyboardEventHandler(
            on_next_image=lambda: self.events_called.append("next"),
            on_prev_image=lambda: self.events_called.append("prev"),
            on_first_image=lambda: self.events_called.append("first"),
            on_last_image=lambda: self.events_called.append("last"),
            on_zoom_in=lambda: self.events_called.append("zoom_in"),
            on_zoom_out=lambda: self.events_called.append("zoom_out"),
            on_reset_zoom=lambda: self.events_called.append("reset_zoom"),
            on_mode_single=lambda: self.events_called.append("mode_single"),
            on_mode_scroll=lambda: self.events_called.append("mode_scroll"),
        )

    def _make_key_event(self, key, modifiers=Qt.KeyboardModifier.NoModifier):
        return QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers)

    def test_mode_keys(self):
        """Key 1 triggers on_mode_single, Key 2 triggers on_mode_scroll."""
        self.events_called.clear()
        handled = self.handler.handle_key_press(self._make_key_event(Qt.Key.Key_1))
        self.assertTrue(handled)
        self.assertEqual(self.events_called, ["mode_single"])

        self.events_called.clear()
        handled = self.handler.handle_key_press(self._make_key_event(Qt.Key.Key_2))
        self.assertTrue(handled)
        self.assertEqual(self.events_called, ["mode_scroll"])

    def test_toggle_mode_fallback_keys(self):
        """When only on_toggle_mode is provided, Key 1 and Key 2 call it."""
        toggle_events = []
        handler = KeyboardEventHandler(
            on_toggle_mode=lambda: toggle_events.append("toggle")
        )
        handled1 = handler.handle_key_press(self._make_key_event(Qt.Key.Key_1))
        self.assertTrue(handled1)
        self.assertEqual(toggle_events, ["toggle"])

        handled2 = handler.handle_key_press(self._make_key_event(Qt.Key.Key_2))
        self.assertTrue(handled2)
        self.assertEqual(toggle_events, ["toggle", "toggle"])

    def test_navigation_next_keys(self):
        """Right, Down, PageDown, and Space trigger on_next_image."""
        for key in (
            Qt.Key.Key_Right,
            Qt.Key.Key_Down,
            Qt.Key.Key_PageDown,
            Qt.Key.Key_Space,
        ):
            self.events_called.clear()
            handled = self.handler.handle_key_press(self._make_key_event(key))
            self.assertTrue(handled)
            self.assertEqual(self.events_called, ["next"])

    def test_navigation_prev_keys(self):
        """Left, Up, PageUp, and Backspace trigger on_prev_image."""
        for key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Up,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_Backspace,
        ):
            self.events_called.clear()
            handled = self.handler.handle_key_press(self._make_key_event(key))
            self.assertTrue(handled)
            self.assertEqual(self.events_called, ["prev"])

    def test_navigation_first_and_last_keys(self):
        """Home triggers on_first_image, End triggers on_last_image."""
        handled = self.handler.handle_key_press(self._make_key_event(Qt.Key.Key_Home))
        self.assertTrue(handled)
        self.assertEqual(self.events_called, ["first"])

        self.events_called.clear()
        handled = self.handler.handle_key_press(self._make_key_event(Qt.Key.Key_End))
        self.assertTrue(handled)
        self.assertEqual(self.events_called, ["last"])

    def test_zoom_keys_with_ctrl(self):
        """Ctrl+Plus, Ctrl+Minus, Ctrl+0 trigger zoom actions."""
        ctrl = Qt.KeyboardModifier.ControlModifier

        # Zoom in (+ / =)
        self.events_called.clear()
        handled = self.handler.handle_key_press(self._make_key_event(Qt.Key.Key_Plus, ctrl))
        self.assertTrue(handled)
        self.assertEqual(self.events_called, ["zoom_in"])

        self.events_called.clear()
        handled = self.handler.handle_key_press(self._make_key_event(Qt.Key.Key_Equal, ctrl))
        self.assertTrue(handled)
        self.assertEqual(self.events_called, ["zoom_in"])

        # Zoom out (- / _)
        self.events_called.clear()
        handled = self.handler.handle_key_press(self._make_key_event(Qt.Key.Key_Minus, ctrl))
        self.assertTrue(handled)
        self.assertEqual(self.events_called, ["zoom_out"])

        # Reset zoom (0)
        self.events_called.clear()
        handled = self.handler.handle_key_press(self._make_key_event(Qt.Key.Key_0, ctrl))
        self.assertTrue(handled)
        self.assertEqual(self.events_called, ["reset_zoom"])

    def test_unhandled_keys(self):
        """Other keys return False and trigger no callbacks."""
        handled = self.handler.handle_key_press(self._make_key_event(Qt.Key.Key_Escape))
        self.assertFalse(handled)
        self.assertEqual(self.events_called, [])


class TestMouseEventHandler(unittest.TestCase):
    """Test suite for MouseEventHandler."""

    def setUp(self):
        self.pan_deltas = []
        self.zoom_events = []
        self.events_called = []
        self.cursor_changes = []

        self.handler = MouseEventHandler(
            on_pan=lambda dx, dy: self.pan_deltas.append((dx, dy)),
            on_zoom_anchor=lambda factor, pos: self.zoom_events.append((factor, pos)),
            on_next_image=lambda: self.events_called.append("next"),
            on_prev_image=lambda: self.events_called.append("prev"),
            on_reset_view=lambda: self.events_called.append("reset"),
            on_cursor_change=lambda cur: self.cursor_changes.append(cur),
            on_toggle_mode=lambda: self.events_called.append("toggle_mode"),
        )

    def _make_mouse_press(self, button, pos=QPointF(100, 100)):
        return QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            pos,
            button,
            button,
            Qt.KeyboardModifier.NoModifier,
        )

    def _make_mouse_move(self, pos=QPointF(150, 120), buttons=Qt.MouseButton.LeftButton):
        return QMouseEvent(
            QMouseEvent.Type.MouseMove,
            pos,
            Qt.MouseButton.NoButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )

    def _make_mouse_release(self, button=Qt.MouseButton.LeftButton, pos=QPointF(150, 120)):
        return QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            pos,
            button,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

    def _make_wheel_event(self, delta_y, modifiers=Qt.KeyboardModifier.NoModifier, pos=QPointF(200, 200)):
        return QWheelEvent(
            pos,
            pos,
            QPoint(0, 0),
            QPoint(0, delta_y),
            Qt.MouseButton.NoButton,
            modifiers,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )

    def test_drag_to_pan(self):
        """Pressing LeftButton and moving drags to pan; releasing stops drag."""
        self.assertFalse(self.handler.is_dragging)

        # Press
        self.handler.handle_mouse_press(self._make_mouse_press(Qt.MouseButton.LeftButton, QPointF(100, 100)))
        self.assertTrue(self.handler.is_dragging)
        self.assertEqual(self.cursor_changes[-1], Qt.CursorShape.ClosedHandCursor)

        # Move
        self.handler.handle_mouse_move(self._make_mouse_move(QPointF(130, 110)))
        self.assertEqual(len(self.pan_deltas), 1)
        self.assertAlmostEqual(self.pan_deltas[0][0], 30.0)
        self.assertAlmostEqual(self.pan_deltas[0][1], 10.0)

        # Move again
        self.handler.handle_mouse_move(self._make_mouse_move(QPointF(120, 105)))
        self.assertEqual(len(self.pan_deltas), 2)
        self.assertAlmostEqual(self.pan_deltas[1][0], -10.0)
        self.assertAlmostEqual(self.pan_deltas[1][1], -5.0)

        # Release
        self.handler.handle_mouse_release(self._make_mouse_release(Qt.MouseButton.LeftButton), is_zoomed=True)
        self.assertFalse(self.handler.is_dragging)
        self.assertEqual(self.cursor_changes[-1], Qt.CursorShape.OpenHandCursor)

    def test_middle_button_and_side_buttons(self):
        """Middle click triggers next image, side buttons navigate."""
        # Middle click (wheel press)
        self.handler.handle_mouse_press(self._make_mouse_press(Qt.MouseButton.MiddleButton))
        self.assertEqual(self.events_called, ["next"])

        # Forward button
        self.events_called.clear()
        self.handler.handle_mouse_press(self._make_mouse_press(Qt.MouseButton.ForwardButton))
        self.assertEqual(self.events_called, ["next"])

        # Back button
        self.events_called.clear()
        self.handler.handle_mouse_press(self._make_mouse_press(Qt.MouseButton.BackButton))
        self.assertEqual(self.events_called, ["prev"])

    def test_right_click_alternates_mode(self):
        """Right click triggers on_toggle_mode."""
        self.events_called.clear()
        handled = self.handler.handle_mouse_press(self._make_mouse_press(Qt.MouseButton.RightButton))
        self.assertTrue(handled)
        self.assertEqual(self.events_called, ["toggle_mode"])

    def test_double_click_resets(self):
        """Double clicking resets view."""
        ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonDblClick,
            QPointF(10, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        handled = self.handler.handle_double_click(ev)
        self.assertTrue(handled)
        self.assertEqual(self.events_called, ["reset"])

    def test_wheel_zoom_with_ctrl(self):
        """Ctrl + Wheel scales image anchored at cursor position."""
        ctrl = Qt.KeyboardModifier.ControlModifier
        # Wheel up (zoom in)
        self.handler.handle_wheel(self._make_wheel_event(120, modifiers=ctrl, pos=QPointF(300, 150)))
        self.assertEqual(len(self.zoom_events), 1)
        factor, pos = self.zoom_events[0]
        self.assertGreater(factor, 1.0)
        self.assertEqual(pos, QPointF(300, 150))

        # Wheel down (zoom out)
        self.handler.handle_wheel(self._make_wheel_event(-120, modifiers=ctrl, pos=QPointF(300, 150)))
        self.assertEqual(len(self.zoom_events), 2)
        factor2, _ = self.zoom_events[1]
        self.assertLess(factor2, 1.0)

    def test_wheel_navigation_without_ctrl(self):
        """Wheel down navigates to next image; wheel up navigates to prev image."""
        # Wheel down (-120) -> next
        self.handler.handle_wheel(self._make_wheel_event(-120))
        self.assertEqual(self.events_called, ["next"])

        # Wheel up (+120) -> prev
        self.events_called.clear()
        self.handler.handle_wheel(self._make_wheel_event(120))
        self.assertEqual(self.events_called, ["prev"])



class DummyViewer:
    """Mock viewer to verify CommonViewerControls.connect_viewer binding."""

    def __init__(self):
        self.panned = []
        self.zoomed_at = []
        self.zoomed_in = 0
        self.zoomed_out = 0
        self.view_reset = 0
        self.cursor_set = []

    def pan_by(self, dx: float, dy: float):
        self.panned.append((dx, dy))

    def zoom_at(self, scale: float, anchor: QPointF):
        self.zoomed_at.append((scale, anchor))

    def zoom_in(self):
        self.zoomed_in += 1

    def zoom_out(self):
        self.zoomed_out += 1

    def reset_view(self):
        self.view_reset += 1

    def setCursor(self, cursor):
        self.cursor_set.append(cursor)


class TestCommonViewerControls(unittest.TestCase):
    """Test suite for CommonViewerControls signal emission and viewer binding."""

    def setUp(self):
        self.controls = CommonViewerControls()

        # Signal capture accumulators
        self.panned = []
        self.zoomed_at = []
        self.zoomed_in = 0
        self.zoomed_out = 0
        self.view_resets = 0
        self.next_images = 0
        self.prev_images = 0
        self.first_images = 0
        self.last_images = 0
        self.toggle_modes = 0
        self.single_modes = 0
        self.scroll_modes = 0
        self.cursor_changes = []

        self.controls.pan_requested.connect(lambda dx, dy: self.panned.append((dx, dy)))
        self.controls.zoom_anchor_requested.connect(lambda s, pt: self.zoomed_at.append((s, pt)))
        self.controls.zoom_in_requested.connect(lambda: setattr(self, "zoomed_in", self.zoomed_in + 1))
        self.controls.zoom_out_requested.connect(lambda: setattr(self, "zoomed_out", self.zoomed_out + 1))
        self.controls.reset_view_requested.connect(lambda: setattr(self, "view_resets", self.view_resets + 1))
        self.controls.next_image_requested.connect(lambda: setattr(self, "next_images", self.next_images + 1))
        self.controls.prev_image_requested.connect(lambda: setattr(self, "prev_images", self.prev_images + 1))
        self.controls.first_image_requested.connect(lambda: setattr(self, "first_images", self.first_images + 1))
        self.controls.last_image_requested.connect(lambda: setattr(self, "last_images", self.last_images + 1))
        self.controls.toggle_mode_requested.connect(lambda: setattr(self, "toggle_modes", self.toggle_modes + 1))
        self.controls.mode_single_requested.connect(lambda: setattr(self, "single_modes", self.single_modes + 1))
        self.controls.mode_scroll_requested.connect(lambda: setattr(self, "scroll_modes", self.scroll_modes + 1))
        self.controls.cursor_change_requested.connect(lambda c: self.cursor_changes.append(c))

    def _make_key(self, key, modifiers=Qt.KeyboardModifier.NoModifier):
        return QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers)

    def _make_mouse_press(self, button, pos=QPointF(100, 100)):
        return QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            pos,
            button,
            button,
            Qt.KeyboardModifier.NoModifier,
        )

    def _make_mouse_move(self, pos, button=Qt.MouseButton.LeftButton):
        return QMouseEvent(
            QMouseEvent.Type.MouseMove,
            pos,
            Qt.MouseButton.NoButton,
            button,
            Qt.KeyboardModifier.NoModifier,
        )

    def _make_mouse_release(self, button=Qt.MouseButton.LeftButton, pos=QPointF(100, 100)):
        return QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            pos,
            button,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

    def _make_wheel(self, delta_y: int, modifiers=Qt.KeyboardModifier.NoModifier, pos=QPointF(200, 200)):
        return QWheelEvent(
            pos,
            pos,
            QPoint(0, 0),
            QPoint(0, delta_y),
            Qt.MouseButton.NoButton,
            modifiers,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )

    def test_mouse_drag_and_release(self):
        """Left drag emits pan_requested and cursor changes."""
        self.controls.handle_mouse_press(self._make_mouse_press(Qt.MouseButton.LeftButton, QPointF(100, 100)))
        self.assertTrue(self.controls.is_dragging)
        self.assertEqual(self.cursor_changes, [Qt.CursorShape.ClosedHandCursor])

        self.controls.handle_mouse_move(self._make_mouse_move(QPointF(125, 110)))
        self.assertEqual(self.panned, [(25.0, 10.0)])

        self.controls.handle_mouse_release(self._make_mouse_release(), is_zoomed=True)
        self.assertFalse(self.controls.is_dragging)
        self.assertEqual(self.cursor_changes[-1], Qt.CursorShape.OpenHandCursor)

    def test_right_click_toggle_mode(self):
        """Right click emits toggle_mode_requested."""
        handled = self.controls.handle_mouse_press(self._make_mouse_press(Qt.MouseButton.RightButton))
        self.assertTrue(handled)
        self.assertEqual(self.toggle_modes, 1)

    def test_navigation_buttons(self):
        """Middle, Forward, Back buttons emit next/prev signals."""
        self.controls.handle_mouse_press(self._make_mouse_press(Qt.MouseButton.MiddleButton))
        self.assertEqual(self.next_images, 1)

        self.controls.handle_mouse_press(self._make_mouse_press(Qt.MouseButton.ForwardButton))
        self.assertEqual(self.next_images, 2)

        self.controls.handle_mouse_press(self._make_mouse_press(Qt.MouseButton.BackButton))
        self.assertEqual(self.prev_images, 1)

    def test_double_click_resets(self):
        """Double click emits reset_view_requested."""
        ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonDblClick,
            QPointF(10, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.controls.handle_double_click(ev)
        self.assertEqual(self.view_resets, 1)

    def test_ctrl_wheel_zoom(self):
        """Ctrl + Wheel emits zoom_anchor_requested."""
        ctrl = Qt.KeyboardModifier.ControlModifier
        handled = self.controls.handle_wheel(self._make_wheel(120, modifiers=ctrl, pos=QPointF(150, 150)))
        self.assertTrue(handled)
        self.assertEqual(len(self.zoomed_at), 1)
        scale, pt = self.zoomed_at[0]
        self.assertGreater(scale, 1.0)
        self.assertEqual(pt, QPointF(150, 150))

    def test_wheel_navigation(self):
        """Wheel down emits next_image_requested, wheel up emits prev_image_requested."""
        self.controls.handle_wheel(self._make_wheel(-120))
        self.assertEqual(self.next_images, 1)

        self.controls.handle_wheel(self._make_wheel(120))
        self.assertEqual(self.prev_images, 1)

    def test_key_mode_switches(self):
        """Key 1 and Key 2 emit mode signals."""
        self.controls.handle_key_press(self._make_key(Qt.Key.Key_1))
        self.assertEqual(self.single_modes, 1)
        self.assertEqual(self.toggle_modes, 1)

        self.controls.handle_key_press(self._make_key(Qt.Key.Key_2))
        self.assertEqual(self.scroll_modes, 1)
        self.assertEqual(self.toggle_modes, 2)

    def test_ctrl_key_zooms(self):
        """Ctrl + Plus/Minus/0 emit zoom signals."""
        ctrl = Qt.KeyboardModifier.ControlModifier
        self.controls.handle_key_press(self._make_key(Qt.Key.Key_Plus, ctrl))
        self.assertEqual(self.zoomed_in, 1)

        self.controls.handle_key_press(self._make_key(Qt.Key.Key_Minus, ctrl))
        self.assertEqual(self.zoomed_out, 1)

        self.controls.handle_key_press(self._make_key(Qt.Key.Key_0, ctrl))
        self.assertEqual(self.view_resets, 1)

    def test_key_navigation(self):
        """Arrows, Home, End emit correct signals."""
        self.controls.handle_key_press(self._make_key(Qt.Key.Key_Right))
        self.assertEqual(self.next_images, 1)

        self.controls.handle_key_press(self._make_key(Qt.Key.Key_Left))
        self.assertEqual(self.prev_images, 1)

        self.controls.handle_key_press(self._make_key(Qt.Key.Key_Home))
        self.assertEqual(self.first_images, 1)

        self.controls.handle_key_press(self._make_key(Qt.Key.Key_End))
        self.assertEqual(self.last_images, 1)

    def test_connect_viewer_binding(self):
        """connect_viewer correctly links signals to viewer methods."""
        viewer = DummyViewer()
        self.controls.connect_viewer(viewer)

        self.controls.pan_requested.emit(15.0, -5.0)
        self.assertEqual(viewer.panned, [(15.0, -5.0)])

        self.controls.zoom_anchor_requested.emit(1.2, QPointF(50, 60))
        self.assertEqual(viewer.zoomed_at, [(1.2, QPointF(50, 60))])

        self.controls.zoom_in_requested.emit()
        self.assertEqual(viewer.zoomed_in, 1)

        self.controls.zoom_out_requested.emit()
        self.assertEqual(viewer.zoomed_out, 1)

        self.controls.reset_view_requested.emit()
        self.assertEqual(viewer.view_reset, 1)

        self.controls.cursor_change_requested.emit(Qt.CursorShape.PointingHandCursor)
        self.assertEqual(viewer.cursor_set, [Qt.CursorShape.PointingHandCursor])


if __name__ == "__main__":
    unittest.main()

