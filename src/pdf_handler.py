"""Auxiliary module for PDF document interactions using pypdfium2.

Provides thread-safe PDF page acquisition, size querying, and rendering to QImage
compatible with the Qt Scroll Reader continuous and single-page viewing pipelines.
"""

from __future__ import annotations

import os
import threading
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImage

try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None  # type: ignore


MIB = 1024 * 1024


class PdfDocumentHandler:
    """Thread-safe handler for interacting with a single PDF document using pypdfium2."""

    MAX_RENDER_BYTES = 64 * MIB

    def __init__(self, file_path: str):
        if pdfium is None:
            raise RuntimeError(
                "pypdfium2 is not installed. Please install it with 'pip install pypdfium2'."
            )

        self.file_path = os.path.abspath(file_path)
        if not os.path.isfile(self.file_path):
            raise FileNotFoundError(f"PDF file not found: '{self.file_path}'")

        self._lock = threading.RLock()
        with self._lock:
            self._doc = pdfium.PdfDocument(self.file_path)
            self._page_count = len(self._doc)
            self._sizes_cache: Dict[int, QSize] = {}

    @property
    def page_count(self) -> int:
        """Return the number of pages in the PDF document."""
        return self._page_count

    @property
    def filename(self) -> str:
        """Return the base filename of the PDF document."""
        return os.path.basename(self.file_path)

    def get_page_size(self, page_index: int) -> QSize:
        """Return native page dimensions as a QSize (in points/pixels). Cached for O(1) access."""
        with self._lock:
            if page_index in self._sizes_cache:
                return self._sizes_cache[page_index]

            if not (0 <= page_index < self._page_count):
                raise IndexError(
                    f"Page index {page_index} out of range (0..{self._page_count - 1})"
                )

            # The document-level API reads the page box without opening a page.
            # Opening every page just to query its size makes PDFium retain large
            # image streams for image-only PDFs.
            width, height = self._doc.get_page_size(page_index)
            size = QSize(max(1, int(round(width))), max(1, int(round(height))))

            self._sizes_cache[page_index] = size
            return size

    def get_all_page_sizes(self) -> List[QSize]:
        """Return dimensions for all pages in the PDF."""
        return [self.get_page_size(i) for i in range(self._page_count)]

    def render_page(
        self,
        page_index: int,
        bounds: Optional[QSize] = None,
        scale: Optional[float] = None,
    ) -> QImage:
        """Render a PDF page to a QImage, sized to bounds while strictly preserving aspect ratio.

        The returned QImage owns its memory buffer and is completely detached from pypdfium2.
        """
        with self._lock:
            if not (0 <= page_index < self._page_count):
                raise IndexError(
                    f"Page index {page_index} out of range (0..{self._page_count - 1})"
                )

            # Keep the cached document lightweight. PDFium may retain image and
            # page data for the lifetime of a document, so rendering every page
            # through self._doc makes memory grow with the number of viewed pages.
            # A short-lived render document releases that data after each page.
            render_doc = pdfium.PdfDocument(self.file_path)
            try:
                page = render_doc[page_index]
                try:
                    pw, ph = page.get_size()
                    if pw <= 0 or ph <= 0:
                        pw, ph = 600.0, 800.0

                    if bounds is not None and bounds.isValid() and bounds.width() > 0 and bounds.height() > 0:
                        scaled = QSize(int(round(pw)), int(round(ph))).scaled(
                            bounds, Qt.AspectRatioMode.KeepAspectRatio
                        )
                        render_scale = scaled.width() / pw
                    elif scale is not None and scale > 0:
                        render_scale = scale
                    else:
                        # Default render scale 2.0 (~144 DPI) for crisp viewing
                        render_scale = 2.0

                    # Cap scale to avoid pathological memory allocations (max 8192px on any dimension)
                    max_dim = max(pw * render_scale, ph * render_scale)
                    if max_dim > 8192:
                        render_scale = render_scale * (8192.0 / max_dim)

                    # Bound the detached QImage even for extreme zoom levels. Four
                    # bytes per pixel is the worst-case format used below.
                    estimated_bytes = pw * ph * render_scale * render_scale * 4
                    if estimated_bytes > self.MAX_RENDER_BYTES:
                        render_scale *= (self.MAX_RENDER_BYTES / estimated_bytes) ** 0.5

                    bitmap = page.render(scale=render_scale)
                    try:
                        mode = bitmap.mode
                        if mode == "BGR":
                            qfmt = QImage.Format.Format_BGR888
                        elif mode == "BGRA":
                            qfmt = QImage.Format.Format_ARGB32_Premultiplied
                        elif mode == "RGB":
                            qfmt = QImage.Format.Format_RGB888
                        elif mode == "RGBA":
                            qfmt = QImage.Format.Format_RGBA8888
                        else:
                            qfmt = QImage.Format.Format_RGBA8888

                        # Crucial: .copy() creates an independent Qt-managed memory buffer
                        image = QImage(
                            bitmap.buffer,
                            bitmap.width,
                            bitmap.height,
                            bitmap.stride,
                            qfmt,
                        ).copy()
                        return image
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            finally:
                render_doc.close()

    def get_metadata(self) -> dict:
        """Extract document metadata dictionary."""
        with self._lock:
            meta = {}
            if hasattr(self._doc, "get_metadata_dict"):
                try:
                    meta = self._doc.get_metadata_dict()
                except Exception:
                    pass
            return meta

    def close(self) -> None:
        """Close the PDF document handle and free C resources."""
        with self._lock:
            if hasattr(self, "_doc") and self._doc is not None:
                try:
                    self._doc.close()
                except Exception:
                    pass
                self._doc = None


# Global thread-safe document cache so decoding workers can reuse open handles
_DOC_CACHE_LOCK = threading.RLock()
_DOCUMENT_CACHE: Dict[str, PdfDocumentHandler] = {}


def is_pdf_file(path: Optional[str]) -> bool:
    """Check whether a given path points to an existing PDF file."""
    if not path or not isinstance(path, str):
        return False
    resolved = os.path.abspath(path)
    if not os.path.isfile(resolved):
        return False
    ext = os.path.splitext(resolved)[1].lower()
    if ext == ".pdf":
        return True
    try:
        with open(resolved, "rb") as f:
            header = f.read(5)
            return header.startswith(b"%PDF-")
    except OSError:
        return False


def build_pdf_page_uri(pdf_path: str, page_index: int) -> str:
    """Create a canonical page URI representing a specific page within a PDF document."""
    return f"{os.path.abspath(pdf_path)}#page={page_index}"


def parse_pdf_page_uri(uri: str) -> Optional[Tuple[str, int]]:
    """Parse a page URI, returning (pdf_path, page_index) if valid, or None."""
    if not uri or "#page=" not in uri:
        return None
    parts = uri.split("#page=")
    if len(parts) != 2:
        return None
    pdf_path = parts[0]
    try:
        page_index = int(parts[1])
        return pdf_path, page_index
    except ValueError:
        return None


def get_file_path_for_stat(path_or_uri: str) -> str:
    """Resolve the underlying filesystem path to check modification time / size."""
    parsed = parse_pdf_page_uri(path_or_uri)
    if parsed is not None:
        return parsed[0]
    return path_or_uri


def get_pdf_handler(pdf_path: str) -> PdfDocumentHandler:
    """Get or create a cached PdfDocumentHandler for the given PDF file."""
    abs_path = os.path.abspath(pdf_path)
    with _DOC_CACHE_LOCK:
        handler = _DOCUMENT_CACHE.get(abs_path)
        if handler is None:
            handler = PdfDocumentHandler(abs_path)
            _DOCUMENT_CACHE[abs_path] = handler
        return handler


def close_pdf_handler(pdf_path: str) -> None:
    """Close and remove a cached PdfDocumentHandler."""
    abs_path = os.path.abspath(pdf_path)
    with _DOC_CACHE_LOCK:
        handler = _DOCUMENT_CACHE.pop(abs_path, None)
        if handler is not None:
            handler.close()


def close_all_pdf_handlers() -> None:
    """Close and evict all cached PDF handlers."""
    with _DOC_CACHE_LOCK:
        for handler in _DOCUMENT_CACHE.values():
            handler.close()
        _DOCUMENT_CACHE.clear()


def get_pdf_page_size(pdf_path: str, page_index: int) -> QSize:
    """Query dimensions of a PDF page."""
    handler = get_pdf_handler(pdf_path)
    return handler.get_page_size(page_index)


def render_pdf_page(
    pdf_path: str, page_index: int, bounds: Optional[QSize] = None
) -> Tuple[QImage, QSize, str]:
    """Render a PDF page for worker threads, returning (image, source_size, error_message)."""
    try:
        handler = get_pdf_handler(pdf_path)
        source_size = handler.get_page_size(page_index)
        image = handler.render_page(page_index, bounds=bounds)
        return image, source_size, ""
    except Exception as e:
        return QImage(), QSize(), str(e)
