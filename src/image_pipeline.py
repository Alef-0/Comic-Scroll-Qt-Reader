"""Bounded, asynchronous image decoding for the Qt image viewer."""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from typing import Hashable, Optional, Set

from PyQt6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QImageReader

try:
    from src.pdf_handler import (
        get_file_path_for_stat,
        parse_pdf_page_uri,
        render_pdf_page,
    )
except ImportError:
    from pdf_handler import (
        get_file_path_for_stat,
        parse_pdf_page_uri,
        render_pdf_page,
    )


MIB = 1024 * 1024


@dataclass(frozen=True)
class CachedImage:
    """Decoded pixels plus the dimensions reported by the source file."""

    image: QImage
    source_size: QSize


class ByteBoundedImageCache:
    """Least-recently-used QImage cache limited by decoded bytes, not item count."""

    def __init__(self, byte_limit: int):
        self.byte_limit = max(0, byte_limit)
        self._items: OrderedDict[Hashable, CachedImage] = OrderedDict()
        self._bytes = 0

    @property
    def bytes_used(self) -> int:
        return self._bytes

    def get(self, key: Hashable) -> Optional[CachedImage]:
        item = self._items.get(key)
        if item is not None:
            self._items.move_to_end(key)
        return item

    def get_covering_preview(
        self, path: str, signature: tuple, bounds: QSize
    ) -> Optional[CachedImage]:
        """Return the smallest cached variant that covers the requested preview."""
        candidates = []
        for key, item in self._items.items():
            if (
                not isinstance(key, tuple)
                or len(key) < 3
                or key[0] != path
                or key[1] != signature
                or key[2] is None
            ):
                continue

            required_size = item.source_size.scaled(
                bounds, Qt.AspectRatioMode.KeepAspectRatio
            )
            if (
                required_size.width() > item.source_size.width()
                or required_size.height() > item.source_size.height()
            ):
                required_size = item.source_size

            if (
                item.image.width() >= required_size.width()
                and item.image.height() >= required_size.height()
                and int(item.image.sizeInBytes())
                <= max(1, required_size.width() * required_size.height() * 4) * 2
            ):
                candidates.append((int(item.image.sizeInBytes()), key, item))

        if not candidates:
            return None

        _, key, item = min(candidates, key=lambda candidate: candidate[0])
        self._items.move_to_end(key)
        return item

    def put(self, key: Hashable, item: CachedImage) -> None:
        image_bytes = int(item.image.sizeInBytes())

        if self.byte_limit == 0 or image_bytes > self.byte_limit:
            return

        if isinstance(key, tuple) and len(key) >= 3 and key[2] is not None:
            for existing_key, existing_item in self._items.items():
                if (
                    isinstance(existing_key, tuple)
                    and len(existing_key) >= 3
                    and existing_key[0] == key[0]
                    and existing_key[1] == key[1]
                    and existing_item.image.width() >= item.image.width()
                    and existing_item.image.height() >= item.image.height()
                    and int(existing_item.image.sizeInBytes()) <= image_bytes * 2
                ):
                    return

        previous = self._items.pop(key, None)
        if previous is not None:
            self._bytes -= int(previous.image.sizeInBytes())

        # Keep only one decoded preview size per file. A covering larger image is
        # reused by get_covering_preview(), while a newly decoded larger variant
        # replaces its smaller predecessor.
        if isinstance(key, tuple) and len(key) >= 3 and key[2] is not None:
            for existing_key in list(self._items):
                if (
                    isinstance(existing_key, tuple)
                    and existing_key
                    and existing_key[0] == key[0]
                ):
                    evicted = self._items.pop(existing_key)
                    self._bytes -= int(evicted.image.sizeInBytes())

        self._items[key] = item
        self._bytes += image_bytes
        while self._bytes > self.byte_limit and self._items:
            _, evicted = self._items.popitem(last=False)
            self._bytes -= int(evicted.image.sizeInBytes())

    def retain_paths(self, paths: set[str]) -> None:
        """Discard cached variants whose absolute source path is not retained."""
        for key in list(self._items):
            if not isinstance(key, tuple) or not key or key[0] not in paths:
                evicted = self._items.pop(key)
                self._bytes -= int(evicted.image.sizeInBytes())

    def clear(self) -> None:
        self._items.clear()
        self._bytes = 0


@dataclass(frozen=True)
class DecodeRequest:
    request_id: int
    path: str
    purpose: str
    bounds: Optional[QSize]
    cache_key: tuple


@dataclass(frozen=True)
class DecodeResult:
    request: DecodeRequest
    image: QImage
    source_size: QSize
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return not self.image.isNull() and not self.error


class _WorkerSignals(QObject):
    finished = pyqtSignal(int, object)


class _DecodeWorker(QRunnable):
    """Decode one image. The worker creates QImage only, never a GUI QPixmap."""

    def __init__(self, worker_id: int, request: DecodeRequest):
        super().__init__()
        self.setAutoDelete(False)
        self.worker_id = worker_id
        self.request = request
        self.signals = _WorkerSignals()

    def run(self) -> None:
        pdf_info = parse_pdf_page_uri(self.request.path)
        if pdf_info is not None:
            pdf_path, page_idx = pdf_info
            image, source_size, error = render_pdf_page(
                pdf_path, page_idx, bounds=self.request.bounds
            )
            try:
                self.signals.finished.emit(
                    self.worker_id,
                    DecodeResult(self.request, image, QSize(source_size), error),
                )
            except RuntimeError:
                pass
            return

        reader = QImageReader(self.request.path)
        reader.setAutoTransform(True)
        source_size = reader.size()

        bounds = self.request.bounds
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
        error = "" if not image.isNull() else reader.errorString()
        if not image.isNull():
            if bounds is None or not source_size.isValid():
                source_size = image.size()
            else:
                # QImageReader.size() can describe the unrotated pixel array even
                # when autoTransform() rotates the decoded preview from EXIF data.
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

        try:
            self.signals.finished.emit(
                self.worker_id,
                DecodeResult(self.request, image, QSize(source_size), error),
            )
        except RuntimeError:
            pass


class ImagePipeline(QObject):
    """Prioritized decoder with stale-result-safe request identifiers."""

    image_ready = pyqtSignal(object)
    image_failed = pyqtSignal(object)

    PREVIEW_CACHE_BYTES = 64 * MIB
    MAX_FULL_IMAGE_BYTES = 256 * MIB

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        # PDFium rendering is serialized by PdfDocumentHandler. Keeping PDF jobs
        # on one reusable worker also prevents multiple thread-local allocator
        # arenas from retaining a full-resolution source-page high-water mark.
        self.pdf_pool = QThreadPool(self)
        self.pdf_pool.setMaxThreadCount(1)
        self.preview_cache = ByteBoundedImageCache(self.PREVIEW_CACHE_BYTES)
        self._workers: dict[int, _DecodeWorker] = {}
        self._worker_pools: dict[int, QThreadPool] = {}
        self._inflight_waiters: dict[tuple, list[DecodeRequest]] = {}
        self._worker_ids_by_cache_key: dict[tuple, int] = {}
        self._worker_priorities: dict[int, int] = {}
        self._next_worker_id = 0

        # Reject pathological allocations before Qt attempts to create them.
        QImageReader.setAllocationLimit(self.MAX_FULL_IMAGE_BYTES // MIB)

    def request_preview(
        self,
        path: str,
        bounds: QSize,
        request_id: int,
        purpose: str = "current-preview",
        priority: int = 0,
    ) -> None:
        self._request(path, QSize(bounds), request_id, purpose, priority)

    def request_full(self, path: str, request_id: int) -> None:
        self._request(path, None, request_id, "current-full", 1)

    def cancel_queued(self, purposes: Optional[Set[str]] = None) -> None:
        """Cancel matching consumers without disturbing unrelated shared work.

        Queued workers are removed when none of their consumers remain. Running
        decodes finish, but their cancelled consumers no longer receive results.
        Passing no purposes preserves the original cancel-all behaviour.
        """
        for worker_id, worker in list(self._workers.items()):
            cache_key = worker.request.cache_key
            waiting_requests = self._inflight_waiters.get(cache_key, [])
            if purposes is not None:
                remaining_requests = [
                    request
                    for request in waiting_requests
                    if request.purpose not in purposes
                ]
                if remaining_requests:
                    self._inflight_waiters[cache_key] = remaining_requests
                    continue

            # Leave an empty waiter list behind for a running decode. A later
            # request for the same pixels can then attach to that work safely.
            self._inflight_waiters[cache_key] = []
            worker_pool = self._worker_pools.get(worker_id, self.pool)
            if worker_pool.tryTake(worker):
                self._workers.pop(worker_id, None)
                self._worker_pools.pop(worker_id, None)
                self._inflight_waiters.pop(cache_key, None)
                self._worker_ids_by_cache_key.pop(cache_key, None)
                self._worker_priorities.pop(worker_id, None)

    def promote_queued(
        self, path: str, bounds: QSize, priority: int
    ) -> bool:
        """Raise a matching queued preview's priority when it becomes visible."""
        stat_path = get_file_path_for_stat(path)
        try:
            stat_result = os.stat(stat_path)
        except OSError:
            return False

        cache_key = (
            path,
            (stat_result.st_mtime_ns, stat_result.st_size),
            (bounds.width(), bounds.height()),
        )
        worker_id = self._worker_ids_by_cache_key.get(cache_key)
        return self._promote_cache_key(cache_key, worker_id, priority)

    def _promote_cache_key(
        self, cache_key: tuple, worker_id: Optional[int], priority: int
    ) -> bool:
        if worker_id is None:
            return False

        current_priority = self._worker_priorities.get(worker_id, 0)
        if priority <= current_priority:
            return True

        worker = self._workers.get(worker_id)
        worker_pool = self._worker_pools.get(worker_id, self.pool)
        if worker is None or not worker_pool.tryTake(worker):
            return False

        self._worker_priorities[worker_id] = priority
        worker_pool.start(worker, priority)
        return True

    def retain_preview_paths(self, paths: set[str]) -> None:
        self.preview_cache.retain_paths(set(paths))

    def _safe_emit_failed(self, result: DecodeResult) -> None:
        try:
            self.image_failed.emit(result)
        except RuntimeError:
            pass

    def _safe_emit_ready(self, result: DecodeResult) -> None:
        try:
            self.image_ready.emit(result)
        except RuntimeError:
            pass

    def _request(
        self,
        path: str,
        bounds: Optional[QSize],
        request_id: int,
        purpose: str,
        priority: int,
    ) -> None:
        stat_path = get_file_path_for_stat(path)
        try:
            stat_result = os.stat(stat_path)
            signature = (stat_result.st_mtime_ns, stat_result.st_size)
        except OSError as error:
            request = DecodeRequest(
                request_id, path, purpose, bounds, (path,)
            )
            result = DecodeResult(request, QImage(), QSize(), str(error))
            QTimer.singleShot(0, lambda result=result: self._safe_emit_failed(result))
            return

        size_key = None if bounds is None else (bounds.width(), bounds.height())
        cache_key = (path, signature, size_key)
        request = DecodeRequest(
            request_id, path, purpose, bounds, cache_key
        )

        if bounds is not None:
            cached = self.preview_cache.get(cache_key)
            if cached is None:
                cached = self.preview_cache.get_covering_preview(
                    path, signature, bounds
                )
            if cached is not None:
                result = DecodeResult(
                    request, cached.image, QSize(cached.source_size)
                )
                QTimer.singleShot(0, lambda result=result: self._safe_emit_ready(result))
                return

        if cache_key in self._inflight_waiters:
            self._inflight_waiters[cache_key].append(request)
            self._promote_cache_key(
                cache_key,
                self._worker_ids_by_cache_key.get(cache_key),
                priority,
            )
            return

        self._next_worker_id += 1
        worker_id = self._next_worker_id
        worker = _DecodeWorker(worker_id, request)
        worker_pool = (
            self.pdf_pool if parse_pdf_page_uri(path) is not None else self.pool
        )
        self._workers[worker_id] = worker
        self._worker_pools[worker_id] = worker_pool
        self._inflight_waiters[cache_key] = [request]
        self._worker_ids_by_cache_key[cache_key] = worker_id
        self._worker_priorities[worker_id] = priority
        worker.signals.finished.connect(
            self._on_finished, Qt.ConnectionType.QueuedConnection
        )
        worker_pool.start(worker, priority)

    def _on_finished(self, worker_id: int, result: DecodeResult) -> None:
        self._workers.pop(worker_id, None)
        self._worker_pools.pop(worker_id, None)
        self._worker_ids_by_cache_key.pop(result.request.cache_key, None)
        self._worker_priorities.pop(worker_id, None)
        waiting_requests = self._inflight_waiters.pop(
            result.request.cache_key, [result.request]
        )

        if (
            waiting_requests
            and result.succeeded
            and result.request.bounds is not None
        ):
            self.preview_cache.put(
                result.request.cache_key,
                CachedImage(result.image, QSize(result.source_size)),
            )
        for waiting_request in waiting_requests:
            waiting_result = DecodeResult(
                waiting_request,
                result.image,
                QSize(result.source_size),
                result.error,
            )
            if waiting_result.succeeded:
                self.image_ready.emit(waiting_result)
            else:
                self.image_failed.emit(waiting_result)
