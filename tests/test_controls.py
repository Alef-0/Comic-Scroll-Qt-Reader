"""Unit tests for KeyboardEventHandler and MouseEventHandler."""

import unittest
from PyQt6.QtCore import Qt, QPointF, QPoint
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication

from src.controls.events import KeyboardEventHandler, MouseEventHandler

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
        )

    def _make_key_event(self, key, modifiers=Qt.KeyboardModifier.NoModifier):
        return QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers)

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


if __name__ == "__main__":
    unittest.main()
