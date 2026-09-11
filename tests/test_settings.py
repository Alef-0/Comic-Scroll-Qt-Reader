"""Tests for persistent reader state."""

import json
from typing import Generator

import pytest
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from comic_scroll_reader.core.models import ComicMode, ViewerMode
from comic_scroll_reader.core.settings import load_state, save_state, state_file_path
from comic_scroll_reader.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    app = QApplication.instance() or QApplication([])
    yield app


def dispose_window(window: MainWindow, qapp: QApplication) -> None:
    window.shutdown()
    window.deleteLater()
    qapp.processEvents()


def test_settings_round_trip_uses_configured_directory():
    state = {
        "viewer_mode": "scroll",
        "layout": {"maintain_ratios_in_scroll": True},
    }

    assert save_state(state) is True
    assert state_file_path().parent.name == "comic-scroll-reader"
    assert load_state()["viewer_mode"] == "scroll"
    assert load_state()["layout"]["maintain_ratios_in_scroll"] is True


def test_invalid_settings_fall_back_to_defaults(qapp: QApplication):
    path = state_file_path()
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")

    window = MainWindow()
    assert window.viewer_mode == ViewerMode.SINGLE
    assert window.comic_mode == ComicMode.DEFAULT
    assert window._maintain_ratios_action.isChecked() is False
    assert window._always_save_options_action.isChecked() is True
    dispose_window(window, qapp)


def test_window_restores_all_reader_options(qapp: QApplication):
    first = MainWindow()
    first.viewer_mode = ViewerMode.SCROLL
    first._directional_pan_action.setChecked(False)
    first._thumbnail_action.setChecked(True)
    first._set_thumbnails_visible(True)
    first._hud_top_action.setChecked(True)
    first._set_hud_at_top(True)
    first._set_thumbnail_layout("horizontal")
    first._hud.set_hud_scale(130)
    first._double_page_action.setChecked(True)
    first._invert_pages_action.setChecked(True)
    first._page_spacing_action.setChecked(False)
    first._double_spread_action.setChecked(False)
    first._apply_custom_layout_options()
    first._maintain_ratios_action.setChecked(True)
    first._apply_scroll_ratio_option()
    first.scroll_reader.set_zoom(1.75)
    assert first.comic_mode == ComicMode.CUSTOM
    dispose_window(first, qapp)

    saved = json.loads(state_file_path().read_text(encoding="utf-8"))
    assert saved["version"] == 1

    restored = MainWindow()
    assert restored.viewer_mode == ViewerMode.SCROLL
    assert restored.comic_mode == ComicMode.CUSTOM
    assert restored._directional_pan_action.isChecked() is False
    assert restored._thumbnail_action.isChecked() is True
    assert restored._hud.thumbnails_visible() is True
    assert restored._hud_top_action.isChecked() is True
    assert restored._hud.is_at_top() is True
    assert restored._hud.thumbnail_layout() == "horizontal"
    assert restored._thumbnail_layout_actions["horizontal"].isChecked() is True
    assert restored._hud.hud_scale() == 130
    assert restored._double_page_action.isChecked() is True
    assert restored._invert_pages_action.isChecked() is True
    assert restored._page_spacing_action.isChecked() is False
    assert restored._double_spread_action.isChecked() is False
    assert restored._maintain_ratios_action.isChecked() is True
    assert restored.scroll_reader.maintain_ratios is True
    assert restored.scroll_reader.zoom_factor == 1.75
    dispose_window(restored, qapp)


def test_disabling_always_save_keeps_only_the_toggle_choice(qapp: QApplication):
    first = MainWindow()
    first._hud.set_hud_scale(145)
    first._thumbnail_action.setChecked(True)
    first._always_save_options_action.setChecked(False)
    dispose_window(first, qapp)

    saved = json.loads(state_file_path().read_text(encoding="utf-8"))
    assert saved == {"version": 1, "always_save_options": False}

    restored = MainWindow()
    assert restored._always_save_options_action.isChecked() is False
    assert restored._hud.hud_scale() == 100
    assert restored._thumbnail_action.isChecked() is False
    dispose_window(restored, qapp)


def test_saved_scroll_mode_is_used_when_opening_a_folder(
    qapp: QApplication, tmp_path
):
    image_path = tmp_path / "page.png"
    image = QImage(80, 120, QImage.Format.Format_RGB32)
    assert image.save(str(image_path), "PNG")
    assert save_state(
        {
            "viewer_mode": "scroll",
            "comic_mode": "default",
            "scroll_zoom": 1.75,
        }
    )

    window = MainWindow(target_path=str(tmp_path))

    assert window.viewer_mode == ViewerMode.SCROLL
    assert window._stack.currentWidget() is window.scroll_reader
    assert window.scroll_reader.zoom_factor == 1.75
    dispose_window(window, qapp)
