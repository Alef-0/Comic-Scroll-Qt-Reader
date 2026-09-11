"""Lazy CBZ/CBR page access for Comic Scroll Reader."""

from __future__ import annotations

import logging
import os
import re
import threading
import zipfile
from typing import Dict, Optional, Tuple

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PyQt6.QtGui import QImage, QImageReader

try:
    import rarfile
except ImportError:
    rarfile = None  # type: ignore


logger = logging.getLogger(__name__)

MIB = 1024 * 1024
ARCHIVE_EXTENSIONS = {".cbr", ".cbz"}
ARCHIVE_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
    ".gif",
    ".tif",
    ".tiff",
    ".jfif",
    ".ico",
    ".svg",
    ".tga",
}
ARCHIVE_PAGE_MARKER = "#archive-page="


def _natural_member_key(name: str) -> list:
    normalized = name.replace("\\", "/")
    return [
        int(token) if token.isdigit() else token.casefold()
        for token in re.split(r"(\d+)", normalized)
    ]


def _is_directory(info) -> bool:
    is_dir = getattr(info, "is_dir", None)
    if callable(is_dir):
        return bool(is_dir())
    isdir = getattr(info, "isdir", None)
    if callable(isdir):
        return bool(isdir())
    return str(getattr(info, "filename", "")).endswith(("/", "\\"))


def _is_supported_page(info) -> bool:
    if _is_directory(info) or int(getattr(info, "file_size", 0) or 0) <= 0:
        return False
    normalized = str(info.filename).replace("\\", "/")
    parts = normalized.split("/")
    if "__MACOSX" in parts or parts[-1].startswith("._"):
        return False
    return os.path.splitext(normalized)[1].lower() in ARCHIVE_IMAGE_EXTENSIONS


class ComicArchiveHandler:
    """Thread-safe, page-oriented access to one CBZ or CBR archive."""

    MAX_MEMBER_BYTES = 256 * MIB

    def __init__(self, file_path: str):
        self.file_path = os.path.abspath(file_path)
        if not os.path.isfile(self.file_path):
            raise FileNotFoundError(f"Comic archive not found: '{self.file_path}'")

        extension = os.path.splitext(self.file_path)[1].lower()
        if extension not in ARCHIVE_EXTENSIONS:
            raise ValueError(f"Unsupported comic archive type: '{extension}'")
        if extension == ".cbr" and rarfile is None:
            raise RuntimeError(
                "CBR support requires the 'rarfile' package. Install the project "
                "requirements and try again."
            )

        self._lock = threading.RLock()
        self.archive_kind = "CBZ" if extension == ".cbz" else "CBR"
        try:
            self._archive = (
                zipfile.ZipFile(self.file_path, "r")
                if extension == ".cbz"
                else rarfile.RarFile(self.file_path, "r")
            )
            infos = self._archive.infolist()
        except Exception:
            archive = getattr(self, "_archive", None)
            if archive is not None:
                archive.close()
            raise

        self._page_infos = sorted(
            (
                info
                for info in infos
                if _is_supported_page(info)
            ),
            key=lambda info: _natural_member_key(str(info.filename)),
        )
        self._sizes_cache: Dict[int, QSize] = {}
        logger.debug(
            "Archive opened: kind=%s path=%s image_pages=%d",
            self.archive_kind,
            self.file_path,
            len(self._page_infos),
        )

    @property
    def page_count(self) -> int:
        return len(self._page_infos)

    @property
    def filename(self) -> str:
        return os.path.basename(self.file_path)

    def get_page_name(self, page_index: int) -> str:
        return str(self._page_info(page_index).filename)

    def get_page_data(self, page_index: int) -> bytes:
        """Return an independent copy of a page for decoders that need a device."""
        return self._read_page_data(page_index)

    def _page_info(self, page_index: int):
        if not (0 <= page_index < self.page_count):
            raise IndexError(
                f"Page index {page_index} out of range (0..{self.page_count - 1})"
            )
        return self._page_infos[page_index]

    def _read_page_data(self, page_index: int) -> bytes:
        info = self._page_info(page_index)
        declared_size = int(getattr(info, "file_size", 0) or 0)
        if declared_size > self.MAX_MEMBER_BYTES:
            raise ValueError(
                f"Archive page is too large to decode safely: {declared_size} bytes"
            )

        logger.debug(
            "Archive page read started: kind=%s page=%d member=%s compressed_bytes=%s",
            self.archive_kind,
            page_index + 1,
            info.filename,
            getattr(info, "compress_size", "unknown"),
        )
        with self._lock:
            try:
                data = self._archive.read(info)
            except Exception as error:
                if self.archive_kind == "CBR" and type(error).__name__ == "RarCannotExec":
                    raise RuntimeError(
                        "No supported RAR extractor was found. Install unrar "
                        "(recommended), unar, 7zip, or bsdtar and try again."
                    ) from error
                raise
        if len(data) > self.MAX_MEMBER_BYTES:
            raise ValueError(
                f"Archive page is too large to decode safely: {len(data)} bytes"
            )
        return data

    @staticmethod
    def _reader_for_data(data: bytes) -> tuple[QImageReader, QBuffer, QByteArray]:
        byte_array = QByteArray(data)
        buffer = QBuffer(byte_array)
        if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
            raise OSError("Could not open the archive page image buffer")
        reader = QImageReader(buffer)
        reader.setAutoTransform(True)
        return reader, buffer, byte_array

    def get_page_size(self, page_index: int) -> QSize:
        with self._lock:
            cached = self._sizes_cache.get(page_index)
        if cached is not None:
            return QSize(cached)

        data = self._read_page_data(page_index)
        reader, buffer, byte_array = self._reader_for_data(data)
        try:
            size = reader.size()
            if not size.isValid() or size.width() <= 0 or size.height() <= 0:
                raise ValueError(
                    f"Could not read image dimensions for '{self.get_page_name(page_index)}': "
                    f"{reader.errorString()}"
                )
        finally:
            buffer.close()
        del byte_array

        with self._lock:
            self._sizes_cache[page_index] = QSize(size)
        return size

    def decode_page(
        self, page_index: int, bounds: Optional[QSize] = None
    ) -> tuple[QImage, QSize]:
        data = self._read_page_data(page_index)
        reader, buffer, byte_array = self._reader_for_data(data)
        try:
            source_size = reader.size()
            if not source_size.isValid():
                source_size = QSize()

            if source_size.isValid() and bounds is not None and bounds.isValid():
                decoded_size = source_size.scaled(
                    bounds, Qt.AspectRatioMode.KeepAspectRatio
                )
                if (
                    decoded_size.isValid()
                    and decoded_size.width() <= source_size.width()
                    and decoded_size.height() <= source_size.height()
                    and decoded_size != source_size
                ):
                    reader.setScaledSize(decoded_size)

            image = reader.read()
            if image.isNull():
                raise ValueError(
                    f"Could not decode '{self.get_page_name(page_index)}': "
                    f"{reader.errorString()}"
                )
        finally:
            buffer.close()
        del byte_array

        if not source_size.isValid():
            source_size = image.size()
        elif bounds is not None:
            same_orientation_error = abs(
                source_size.width() * image.height()
                - source_size.height() * image.width()
            )
            swapped_orientation_error = abs(
                source_size.height() * image.height()
                - source_size.width() * image.width()
            )
            if swapped_orientation_error < same_orientation_error:
                source_size.transpose()

        logger.debug(
            "Archive page decoded: kind=%s page=%d member=%s source=%dx%d output=%dx%d",
            self.archive_kind,
            page_index + 1,
            self.get_page_name(page_index),
            source_size.width(),
            source_size.height(),
            image.width(),
            image.height(),
        )
        return image, source_size

    def close(self) -> None:
        with self._lock:
            archive = getattr(self, "_archive", None)
            if archive is not None:
                archive.close()
                self._archive = None


_ARCHIVE_CACHE_LOCK = threading.RLock()
_ARCHIVE_CACHE: Dict[str, ComicArchiveHandler] = {}


def is_comic_archive_file(path: Optional[str]) -> bool:
    if not path or not isinstance(path, str):
        return False
    resolved = os.path.abspath(path)
    return (
        os.path.isfile(resolved)
        and os.path.splitext(resolved)[1].lower() in ARCHIVE_EXTENSIONS
    )


def build_archive_page_uri(archive_path: str, page_index: int) -> str:
    return f"{os.path.abspath(archive_path)}{ARCHIVE_PAGE_MARKER}{page_index}"


def parse_archive_page_uri(uri: str) -> Optional[Tuple[str, int]]:
    if not uri or ARCHIVE_PAGE_MARKER not in uri:
        return None
    archive_path, marker, index_text = uri.rpartition(ARCHIVE_PAGE_MARKER)
    if not marker or not archive_path:
        return None
    try:
        return archive_path, int(index_text)
    except ValueError:
        return None


def get_archive_handler(archive_path: str) -> ComicArchiveHandler:
    abs_path = os.path.abspath(archive_path)
    with _ARCHIVE_CACHE_LOCK:
        handler = _ARCHIVE_CACHE.get(abs_path)
        if handler is None:
            handler = ComicArchiveHandler(abs_path)
            _ARCHIVE_CACHE[abs_path] = handler
        return handler


def close_archive_handler(archive_path: str) -> None:
    abs_path = os.path.abspath(archive_path)
    with _ARCHIVE_CACHE_LOCK:
        handler = _ARCHIVE_CACHE.pop(abs_path, None)
        if handler is not None:
            handler.close()


def close_all_archive_handlers() -> None:
    with _ARCHIVE_CACHE_LOCK:
        for handler in _ARCHIVE_CACHE.values():
            handler.close()
        _ARCHIVE_CACHE.clear()


def get_archive_page_size(archive_path: str, page_index: int) -> QSize:
    return get_archive_handler(archive_path).get_page_size(page_index)


def get_archive_page_name(archive_path: str, page_index: int) -> str:
    return get_archive_handler(archive_path).get_page_name(page_index)


def get_archive_page_data(archive_path: str, page_index: int) -> bytes:
    return get_archive_handler(archive_path).get_page_data(page_index)


def decode_archive_page(
    archive_path: str, page_index: int, bounds: Optional[QSize] = None
) -> Tuple[QImage, QSize, str]:
    try:
        image, source_size = get_archive_handler(archive_path).decode_page(
            page_index, bounds=bounds
        )
        return image, source_size, ""
    except Exception as error:
        logger.debug(
            "Archive page decode failed: path=%s page=%d error=%s",
            archive_path,
            page_index + 1,
            error,
        )
        return QImage(), QSize(), str(error)
