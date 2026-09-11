"""Small QMovie owner used by the custom-painted reader widgets."""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QSize, pyqtSignal
from PyQt6.QtGui import QImage, QMovie

from ..media.archive_handler import (
    get_archive_page_data,
    get_archive_page_name,
    parse_archive_page_uri,
)


def is_gif_path(path: Optional[str]) -> bool:
    """Return whether a filesystem or archive-page path names a GIF."""
    if not path:
        return False
    archive_info = parse_archive_page_uri(path)
    if archive_info is None:
        return os.path.splitext(path)[1].lower() == ".gif"

    archive_path, page_index = archive_info
    try:
        member_name = get_archive_page_name(archive_path, page_index)
    except Exception:
        return False
    return os.path.splitext(member_name)[1].lower() == ".gif"


class GifAnimation(QObject):
    """Own a QMovie and any backing archive buffer for its full lifetime."""

    frame_changed = pyqtSignal()

    def __init__(self, path: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.path = path
        self._bytes: Optional[QByteArray] = None
        self._buffer: Optional[QBuffer] = None

        archive_info = parse_archive_page_uri(path)
        if archive_info is None:
            self.movie = QMovie(path, QByteArray(b"gif"), self)
        else:
            archive_path, page_index = archive_info
            try:
                self._bytes = QByteArray(
                    get_archive_page_data(archive_path, page_index)
                )
                self._buffer = QBuffer(self._bytes)
                if not self._buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                    raise OSError("Could not open GIF archive-page buffer")
                self.movie = QMovie(self._buffer, QByteArray(b"gif"), self)
            except Exception:
                self.movie = QMovie(self)

        self.movie.setCacheMode(QMovie.CacheMode.CacheNone)
        self._source_size = QSize()
        self._started = False
        if self.movie.isValid() and self.movie.jumpToFrame(0):
            self._source_size = self.movie.currentImage().size()
            self.movie.stop()
        self.movie.frameChanged.connect(self._on_frame_changed)

    @property
    def is_valid(self) -> bool:
        return self.movie.isValid()

    @property
    def scaled_size(self) -> QSize:
        return QSize(self.movie.scaledSize())

    @property
    def source_size(self) -> QSize:
        return QSize(self._source_size)

    def set_scaled_size(self, size: QSize) -> None:
        if size.isValid() and size != self.movie.scaledSize():
            self.movie.setScaledSize(QSize(size))

    def current_image(self) -> QImage:
        return self.movie.currentImage()

    def start(self) -> None:
        if not self.is_valid or self._started:
            return
        self._started = True
        self.movie.jumpToFrame(0)
        self.movie.start()

    def stop(self) -> None:
        self.movie.stop()

    def _on_frame_changed(self, _frame_number: int) -> None:
        self.frame_changed.emit()
