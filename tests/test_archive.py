"""Tests for lazy CBZ/CBR support."""

import logging
import os
import tempfile
import zipfile
from types import SimpleNamespace
from typing import Generator

import pytest
from PyQt6.QtCore import QBuffer, QByteArray, QEventLoop, QIODevice, QSize, QTimer
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import QApplication

import comic_scroll_reader.archive_handler as archive_handler_module
from comic_scroll_reader.archive_handler import (
    ComicArchiveHandler,
    build_archive_page_uri,
    close_all_archive_handlers,
    decode_archive_page,
    get_archive_page_size,
    is_comic_archive_file,
    parse_archive_page_uri,
)
from comic_scroll_reader.image_pipeline import DecodeResult, ImagePipeline
from comic_scroll_reader.main_window import MainWindow, ViewerMode
from comic_scroll_reader.single_viewer import ImageViewerWidget


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    app = QApplication.instance() or QApplication([])
    yield app


def _png_bytes(width: int, height: int, color: str) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


@pytest.fixture
def sample_cbz() -> Generator[str, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".cbz", delete=False) as file:
        cbz_path = file.name
    with zipfile.ZipFile(cbz_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("chapter/page10.png", _png_bytes(100, 200, "blue"))
        archive.writestr("chapter/page2.png", _png_bytes(300, 150, "green"))
        archive.writestr("chapter/page1.png", _png_bytes(120, 240, "red"))
        archive.writestr("__MACOSX/chapter/._page1.png", b"resource fork")
        archive.writestr("ComicInfo.xml", "<ComicInfo />")

    yield cbz_path

    close_all_archive_handlers()
    os.remove(cbz_path)


def test_archive_uri_and_detection(sample_cbz: str):
    assert is_comic_archive_file(sample_cbz) is True
    assert is_comic_archive_file("/missing/book.cbz") is False

    uri = build_archive_page_uri(sample_cbz, 2)
    assert parse_archive_page_uri(uri) == (os.path.abspath(sample_cbz), 2)
    assert parse_archive_page_uri("plain-image.png") is None
    assert parse_archive_page_uri(f"{sample_cbz}#archive-page=invalid") is None


def test_cbz_handler_natural_order_size_and_decode(sample_cbz: str):
    handler = ComicArchiveHandler(sample_cbz)
    assert handler.archive_kind == "CBZ"
    assert handler.page_count == 3
    assert handler.get_page_name(0) == "chapter/page1.png"
    assert handler.get_page_name(1) == "chapter/page2.png"
    assert handler.get_page_name(2) == "chapter/page10.png"
    assert handler.get_page_size(0) == QSize(120, 240)

    image, source_size = handler.decode_page(0, bounds=QSize(60, 60))
    assert source_size == QSize(120, 240)
    assert image.size() == QSize(30, 60)
    handler.close()


def test_archive_helpers_report_decode_errors(sample_cbz: str):
    assert get_archive_page_size(sample_cbz, 1) == QSize(300, 150)
    image, size, error = decode_archive_page(sample_cbz, 99)
    assert image.isNull()
    assert not size.isValid()
    assert "out of range" in error


def test_image_pipeline_decodes_archive_page(
    qapp: QApplication,
    sample_cbz: str,
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.DEBUG, logger="comic_scroll_reader.image_pipeline")
    pipeline = ImagePipeline()
    uri = build_archive_page_uri(sample_cbz, 1)
    loop = QEventLoop()
    results = []

    def on_ready(result: DecodeResult):
        results.append(result)
        loop.quit()

    pipeline.image_ready.connect(on_ready)
    pipeline.request_preview(
        uri,
        QSize(150, 150),
        request_id=7,
        purpose="current-preview",
    )
    QTimer.singleShot(2000, loop.quit)
    loop.exec()

    assert len(results) == 1
    assert results[0].succeeded
    assert results[0].source_size == QSize(300, 150)
    assert results[0].image.size() == QSize(150, 75)
    assert "Decode started" in caplog.text
    assert "type=archive" in caplog.text
    pipeline.shutdown()


def test_main_window_opens_cbz_like_pdf(qapp: QApplication, sample_cbz: str):
    window = MainWindow(target_path=sample_cbz)
    assert window.archive_path == os.path.abspath(sample_cbz)
    assert window.pdf_path is None
    assert window.viewer_mode == ViewerMode.SINGLE
    assert len(window.image_list) == 3
    assert all(parse_archive_page_uri(path) for path in window.image_list)

    window.update_title()
    assert os.path.basename(sample_cbz) in window.windowTitle()
    window.set_mode(ViewerMode.SCROLL)
    assert window.viewer_mode == ViewerMode.SCROLL
    window.close()
    assert window.archive_path is None


def test_cbr_handler_with_rarfile_compatible_backend(
    monkeypatch: pytest.MonkeyPatch,
):
    payloads = {
        "page10.png": _png_bytes(10, 20, "blue"),
        "page2.png": _png_bytes(30, 40, "red"),
    }

    class FakeInfo:
        def __init__(self, filename: str):
            self.filename = filename
            self.file_size = len(payloads[filename])
            self.compress_size = self.file_size

        def isdir(self):
            return False

    class FakeRarFile:
        def __init__(self, _path: str, _mode: str):
            self.closed = False

        def infolist(self):
            return [FakeInfo(name) for name in payloads]

        def read(self, info: FakeInfo):
            return payloads[info.filename]

        def close(self):
            self.closed = True

    monkeypatch.setattr(
        archive_handler_module,
        "rarfile",
        SimpleNamespace(RarFile=FakeRarFile),
    )
    with tempfile.NamedTemporaryFile(suffix=".cbr") as file:
        handler = ComicArchiveHandler(file.name)
        assert handler.archive_kind == "CBR"
        assert handler.get_page_name(0) == "page2.png"
        image, source_size = handler.decode_page(0)
        assert image.size() == QSize(30, 40)
        assert source_size == QSize(30, 40)
        handler.close()


def test_missing_cbr_dependency_has_actionable_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(archive_handler_module, "rarfile", None)
    with tempfile.NamedTemporaryFile(suffix=".cbr") as file:
        with pytest.raises(RuntimeError, match="rarfile"):
            ComicArchiveHandler(file.name)


def test_sharpening_emits_debug_message(qapp: QApplication, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG, logger="comic_scroll_reader.single_viewer")
    viewer = ImageViewerWidget()
    viewer.set_preview_pixmap(QPixmap(40, 40), QSize(80, 80), "/tmp/page.png")
    viewer.set_refined_preview_pixmap(QPixmap(80, 80), "/tmp/page.png")

    assert "Sharpen applied" in caplog.text
    assert "stage=refined-preview" in caplog.text
