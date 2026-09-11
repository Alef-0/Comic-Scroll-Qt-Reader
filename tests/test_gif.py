"""Animated GIF playback coverage for both reader surfaces."""

import io
import time
import zipfile

from PIL import Image
import pytest
from PyQt6.QtWidgets import QApplication

from comic_scroll_reader.core.models import ViewerMode
from comic_scroll_reader.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _gif_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 36), "red").save(
        output,
        "GIF",
        save_all=True,
        append_images=[Image.new("RGB", (24, 36), "blue")],
        duration=40,
        loop=0,
    )
    return output.getvalue()


def _wait_until(condition, timeout_ms: int = 2000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000.0
    app = QApplication.instance()
    while time.monotonic() < deadline:
        if condition():
            return True
        if app is not None:
            app.processEvents()
        time.sleep(0.01)
    return condition()


def test_gif_animates_in_single_and_scroll_modes(qapp, tmp_path):
    gif_path = tmp_path / "page.gif"
    gif_path.write_bytes(_gif_bytes())

    window = MainWindow(target_path=str(gif_path))
    window.show()
    assert _wait_until(lambda: str(gif_path) in window.image_viewer._animations)

    single_animation = window.image_viewer._animations[str(gif_path)]
    single_frames = []
    single_animation.frame_changed.connect(
        lambda: single_frames.append(single_animation.movie.currentFrameNumber())
    )
    assert _wait_until(lambda: len(single_frames) >= 2)
    assert set(single_frames).issubset({0, 1})

    window._rotate_current_page(90)
    assert _wait_until(
        lambda: window.image_viewer.pixmap() is not None
        and window.image_viewer.pixmap().width()
        > window.image_viewer.pixmap().height()
    )

    window.set_mode(ViewerMode.SCROLL)
    assert _wait_until(lambda: 0 in window.scroll_reader._animations)
    assert not window.image_viewer._animations

    scroll_animation = window.scroll_reader._animations[0]
    scroll_frames = []
    scroll_animation.frame_changed.connect(
        lambda: scroll_frames.append(scroll_animation.movie.currentFrameNumber())
    )
    assert _wait_until(lambda: len(scroll_frames) >= 2)
    assert 0 in window.scroll_reader._animated_pixmaps
    assert (
        window.scroll_reader._animated_pixmaps[0].width()
        > window.scroll_reader._animated_pixmaps[0].height()
    )

    window.set_mode(ViewerMode.SINGLE)
    assert _wait_until(lambda: str(gif_path) in window.image_viewer._animations)
    assert not window.scroll_reader._animations
    window.close()


def test_archive_gif_animates_in_both_modes(qapp, tmp_path):
    archive_path = tmp_path / "animated.cbz"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("pages/page.gif", _gif_bytes())

    window = MainWindow(target_path=str(archive_path))
    window.show()
    gif_uri = window.image_list[0]
    assert _wait_until(lambda: gif_uri in window.image_viewer._animations)
    assert window.image_viewer._animations[gif_uri].is_valid

    window.set_mode(ViewerMode.SCROLL)
    assert _wait_until(lambda: 0 in window.scroll_reader._animations)
    assert window.scroll_reader._animations[0].is_valid
    window.close()
