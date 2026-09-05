"""Tests for PDF support in Qt Scroll Reader via pypdfium2."""

import os
import tempfile
import threading
from typing import Generator

import pytest
import pypdfium2 as pdfium
from PyQt6.QtCore import QEventLoop, QSize, Qt, QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

import src.pdf_handler as pdf_handler_module
from src.image_pipeline import DecodeResult, ImagePipeline
from src.main import parse_arguments
from src.pdf_handler import (
    PdfDocumentHandler,
    build_pdf_page_uri,
    close_all_pdf_handlers,
    close_pdf_handler,
    get_file_path_for_stat,
    get_pdf_handler,
    get_pdf_page_size,
    is_pdf_file,
    parse_pdf_page_uri,
    render_pdf_page,
)
from src.scroll_reader import ScrollReaderWidget
from src.viewer import MainWindow, ViewerMode


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """Provide a persistent QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def sample_pdf() -> Generator[str, None, None]:
    """Create a temporary 3-page PDF document with distinct page dimensions and colors."""
    doc = pdfium.PdfDocument.new()

    # Page 0: 400x600 (portrait)
    p0 = doc.new_page(width=400, height=600)
    bm0 = p0.render(scale=1.0)
    bm0.fill_rect((255, 0, 0, 255), 0, 0, 200, 300)
    bm0.close()
    p0.close()

    # Page 1: 800x600 (landscape)
    p1 = doc.new_page(width=800, height=600)
    bm1 = p1.render(scale=1.0)
    bm1.fill_rect((0, 255, 0, 255), 0, 0, 400, 300)
    bm1.close()
    p1.close()

    # Page 2: 500x500 (square)
    p2 = doc.new_page(width=500, height=500)
    bm2 = p2.render(scale=1.0)
    bm2.fill_rect((0, 0, 255, 255), 0, 0, 250, 250)
    bm2.close()
    p2.close()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    doc.save(pdf_path)
    doc.close()

    yield pdf_path

    close_all_pdf_handlers()
    if os.path.exists(pdf_path):
        os.remove(pdf_path)


def test_is_pdf_file(sample_pdf: str):
    """Verify is_pdf_file detects PDF files and rejects non-PDFs."""
    assert is_pdf_file(sample_pdf) is True
    assert is_pdf_file("/non/existent/file.pdf") is False
    assert is_pdf_file("") is False
    assert is_pdf_file(None) is False

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"Hello world")
        txt_path = f.name
    try:
        assert is_pdf_file(txt_path) is False
    finally:
        os.remove(txt_path)


def test_pdf_uri_helpers(sample_pdf: str):
    """Test PDF page URI creation, parsing, and stat-path resolution."""
    uri = build_pdf_page_uri(sample_pdf, 2)
    assert uri == f"{os.path.abspath(sample_pdf)}#page=2"

    parsed = parse_pdf_page_uri(uri)
    assert parsed is not None
    pdf_path, page_idx = parsed
    assert pdf_path == os.path.abspath(sample_pdf)
    assert page_idx == 2

    assert parse_pdf_page_uri("not_a_pdf_uri") is None
    assert parse_pdf_page_uri(f"{sample_pdf}#page=invalid") is None

    assert get_file_path_for_stat(uri) == os.path.abspath(sample_pdf)
    assert get_file_path_for_stat("/some/image.png") == "/some/image.png"


def test_pdf_handler_basics(sample_pdf: str):
    """Verify PdfDocumentHandler metadata, page counts, and sizes."""
    handler = PdfDocumentHandler(sample_pdf)
    assert handler.page_count == 3
    assert handler.filename == os.path.basename(sample_pdf)

    # Page dimensions
    s0 = handler.get_page_size(0)
    assert s0 == QSize(400, 600)
    s1 = handler.get_page_size(1)
    assert s1 == QSize(800, 600)
    s2 = handler.get_page_size(2)
    assert s2 == QSize(500, 500)

    all_sizes = handler.get_all_page_sizes()
    assert len(all_sizes) == 3
    assert all_sizes[0] == QSize(400, 600)

    with pytest.raises(IndexError):
        handler.get_page_size(5)

    handler.close()


def test_pdf_handler_rendering(sample_pdf: str):
    """Verify rendering a PDF page to QImage with bounds and scales."""
    handler = PdfDocumentHandler(sample_pdf)

    # Render with bounds: 800x1200 on a 400x600 page (2x scale)
    img = handler.render_page(0, bounds=QSize(800, 1200))
    assert isinstance(img, QImage)
    assert not img.isNull()
    assert img.width() == 800
    assert img.height() == 1200

    # Render with bounds: landscape page 800x600 inside 1200x600
    img_land = handler.render_page(1, bounds=QSize(1200, 600))
    assert not img_land.isNull()
    assert img_land.width() == 800
    assert img_land.height() == 600

    # Render with scale
    img_scaled = handler.render_page(2, scale=1.0)
    assert not img_scaled.isNull()
    assert img_scaled.width() == 500
    assert img_scaled.height() == 500

    # Extreme zoom requests must remain within the decoded-page byte budget.
    handler.MAX_RENDER_BYTES = 1 * 1024 * 1024
    img_bounded = handler.render_page(2, scale=10.0)
    assert not img_bounded.isNull()
    assert img_bounded.sizeInBytes() <= handler.MAX_RENDER_BYTES

    handler.close()


def test_pdf_page_size_does_not_open_page(sample_pdf: str):
    """Page-size lookup must use the lightweight document-level PDFium API."""
    handler = PdfDocumentHandler(sample_pdf)
    real_doc = handler._doc

    class SizeOnlyDocument:
        def get_page_size(self, page_index: int):
            return real_doc.get_page_size(page_index)

        def __getitem__(self, page_index: int):
            raise AssertionError("Page-size lookup opened a PDF page")

        def close(self):
            real_doc.close()

    handler._doc = SizeOnlyDocument()
    assert handler.get_page_size(0) == QSize(400, 600)
    handler.close()


def test_pdf_render_uses_short_lived_document(
    sample_pdf: str, monkeypatch: pytest.MonkeyPatch
):
    """Rendered page resources must be released instead of accumulating in the cache document."""
    handler = PdfDocumentHandler(sample_pdf)
    real_document_type = pdfium.PdfDocument
    render_documents = []

    class TrackingDocument:
        def __init__(self, path: str):
            self.document = real_document_type(path)
            self.closed = False
            render_documents.append(self)

        def __getitem__(self, page_index: int):
            return self.document[page_index]

        def close(self):
            self.closed = True
            self.document.close()

    monkeypatch.setattr(pdf_handler_module.pdfium, "PdfDocument", TrackingDocument)

    image = handler.render_page(0, bounds=QSize(200, 300))
    assert not image.isNull()
    assert len(render_documents) == 1
    assert render_documents[0].closed is True
    handler.close()


def test_pdf_concurrent_rendering(sample_pdf: str):
    """Verify thread-safety of PdfDocumentHandler across multiple worker threads."""
    handler = get_pdf_handler(sample_pdf)
    errors = []
    rendered_images = []
    lock = threading.Lock()

    def worker_job(page_idx: int):
        try:
            img = handler.render_page(page_idx, bounds=QSize(300, 300))
            with lock:
                rendered_images.append((page_idx, img))
        except Exception as e:
            with lock:
                errors.append(e)

    threads = []
    for i in range(12):
        t = threading.Thread(target=worker_job, args=(i % 3,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    assert len(rendered_images) == 12
    for _, img in rendered_images:
        assert not img.isNull()


def test_render_pdf_page_helper(sample_pdf: str):
    """Test render_pdf_page convenience helper."""
    img, size, err = render_pdf_page(sample_pdf, 0, bounds=QSize(200, 300))
    assert err == ""
    assert not img.isNull()
    assert size == QSize(400, 600)
    assert img.width() == 200
    assert img.height() == 300

    # Error case
    err_img, _, err_msg = render_pdf_page(sample_pdf, 99)
    assert err_img.isNull()
    assert "out of range" in err_msg


def test_image_pipeline_pdf(qapp: QApplication, sample_pdf: str):
    """Verify ImagePipeline decodes and caches PDF page URIs asynchronously."""
    pipeline = ImagePipeline()
    uri = build_pdf_page_uri(sample_pdf, 1)

    loop = QEventLoop()
    ready_results = []

    def on_ready(res: DecodeResult):
        ready_results.append(res)
        loop.quit()

    pipeline.image_ready.connect(on_ready)
    pipeline.request_preview(uri, QSize(400, 300), request_id=42, purpose="scroll-1")
    assert pipeline._worker_pools
    assert all(pool is pipeline.pdf_pool for pool in pipeline._worker_pools.values())
    QTimer.singleShot(2000, loop.quit)
    loop.exec()

    assert len(ready_results) == 1
    res = ready_results[0]
    assert res.request.path == uri
    assert res.succeeded
    assert not res.image.isNull()
    assert res.source_size == QSize(800, 600)


def test_scroll_reader_pdf(qapp: QApplication, sample_pdf: str):
    """Verify ScrollReaderWidget sets up layout and dimensions for PDF pages."""
    reader = ScrollReaderWidget()
    reader.resize(1000, 800)
    page_uris = [build_pdf_page_uri(sample_pdf, i) for i in range(3)]
    reader.set_images(page_uris)

    assert reader.image_list == page_uris
    assert len(reader.image_rects) == 3

    # Check that heights preserve aspect ratio
    # target_width at 1000 viewport is 1000 (with default scrollbar/viewport bounds)
    rects = reader.image_rects
    target_w = rects[0].width()
    # Page 0 (400x600): aspect ratio 1.5 -> height = target_w * 1.5
    assert rects[0].height() == int(round(target_w * 1.5))
    # Page 1 (800x600): aspect ratio 0.75 -> height = target_w * 0.75
    assert rects[1].height() == int(round(target_w * 0.75))
    # Page 2 (500x500): aspect ratio 1.0 -> height = target_w
    assert rects[2].height() == target_w

    # Vertical spacing
    assert rects[1].y() == rects[0].y() + rects[0].height() + ScrollReaderWidget.SPACING
    assert rects[2].y() == rects[1].y() + rects[1].height() + ScrollReaderWidget.SPACING

    reader.clear()


def test_main_window_open_pdf(qapp: QApplication, sample_pdf: str):
    """Verify MainWindow opens a PDF by default in Scroll Mode with correct page count."""
    window = MainWindow(target_path=sample_pdf)
    window.resize(1280, 720)

    # Must open by default on scroll mode
    assert window.viewer_mode == ViewerMode.SCROLL
    assert len(window.image_list) == 3
    assert window.current_index in (0, -1)  # -1 before preview decoded, 0 committed

    # Title contains PDF filename and page
    window.update_title()
    title = window.windowTitle()
    assert "Qt Scroll Reader [Scroll]" in title
    assert os.path.basename(sample_pdf) in title

    # Navigation in scroll mode
    window.go_to_index(1)
    assert window._requested_index == 1 or window.current_index == 1

    # Switch to Single mode
    window.set_mode(ViewerMode.SINGLE)
    assert window.viewer_mode == ViewerMode.SINGLE
    window.update_title()
    assert "[Scroll]" not in window.windowTitle()

    # Next / Prev navigation
    window.current_index = 0
    window.next_image()
    assert window._requested_index == 1 or window.current_index == 1
    window.last_image()
    assert window._requested_index == 2 or window.current_index == 2
    window.first_image()
    assert window._requested_index == 0 or window.current_index == 0

    # Toggle mode back to Scroll
    window.toggle_mode()
    assert window.viewer_mode == ViewerMode.SCROLL

    window.close()


def test_cli_parse_pdf():
    """Verify CLI argument parser accepts PDF paths."""
    args = parse_arguments(["comic_issue_01.pdf"])
    assert args.image_path == "comic_issue_01.pdf"
