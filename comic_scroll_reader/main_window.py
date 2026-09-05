"""Main application window for Comic Scroll Reader."""

import os
import re
import sys
from typing import List, Optional, Set

from enum import Enum
from PyQt6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtCore import QEvent, Qt, QSize, pyqtSignal

from .about_dialog import AboutDialog
from .hud_overlay import ViewerHud
from .image_pipeline import DecodeResult, ImagePipeline
from .input_controls import (
    CommonViewerControls,
    KeyboardEventHandler,
    MouseEventHandler,
)
from .pdf_handler import (
    build_pdf_page_uri,
    close_pdf_handler,
    get_pdf_handler,
    is_pdf_file,
    parse_pdf_page_uri,
)
from .resources import APP_ICON_PATH, APP_NAME
from .scroll_reader import ScrollReaderWidget
from .shortcuts_dialog import ShortcutsDialog
from .single_viewer import ImageViewerWidget, ScaledImageLabel
from .welcome_widget import WelcomeWidget



class ViewerMode(Enum):
    SINGLE = "single"
    SCROLL = "scroll"


class ComicMode(Enum):
    COMICS = "comics"
    MANGA = "manga"
    WEBTOON = "webtoon"
    CUSTOM = "custom"

SUPPORTED_EXTENSIONS = {
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


def natural_sort_key(file_path: str) -> list:
    """Sort strings containing numbers in human/natural alphabetical order."""
    filename = os.path.basename(file_path)
    return [
        int(token) if token.isdigit() else token.casefold()
        for token in re.split(r"(\d+)", filename)
    ]



__all__ = [
    "ImageViewerWidget",
    "ScaledImageLabel",
    "ScrollReaderWidget",
    "MainWindow",
    "ViewerMode",
    "ComicMode",
    "SUPPORTED_EXTENSIONS",
    "natural_sort_key",
    "WelcomeWidget",
    "ViewerHud",
]


class MainWindow(QMainWindow):
    """Main window with default 1280x720 dimensions, resizable, supporting folder discovery,
    alphabetical navigation, and zoom/pan controls.
    """

    DEFAULT_WIDTH = 580
    DEFAULT_HEIGHT = 330
    VIEWER_WIDTH = 1280
    VIEWER_HEIGHT = 720
    image_loaded = pyqtSignal(str)
    image_load_failed = pyqtSignal(str)

    def __init__(
        self,
        image_path: Optional[str] = None,
        parent=None,
        target_path: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        # Image pipeline shared across both viewer widgets
        self._image_pipeline = ImagePipeline(self)
        self._shutdown_started = False
        self._image_pipeline.image_ready.connect(self._on_image_ready)
        self._image_pipeline.image_failed.connect(self._on_image_failed)

        # Mode 1: Single image viewer
        self.image_viewer = ImageViewerWidget(self)
        self.viewer = self.image_viewer
        self.image_label = self.image_viewer  # Backwards compatibility alias

        # Mode 2: Continuous scroll reader
        self.scroll_reader = ScrollReaderWidget(self, pipeline=self._image_pipeline)

        # Mode 3 / Empty state: Welcome drop-zone widget
        self.welcome_widget = WelcomeWidget(self)
        self.welcome_widget.open_file_requested.connect(self.open_file_dialog)
        self.welcome_widget.open_folder_requested.connect(self.open_folder_dialog)
        self.welcome_widget.about_requested.connect(self.show_about_dialog)

        # Central widget stack supporting both modes and welcome state
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self.image_viewer)
        self._stack.addWidget(self.scroll_reader)
        self._stack.addWidget(self.welcome_widget)
        self.setCentralWidget(self._stack)

        # Initial mode: Single page mode
        self.viewer_mode = ViewerMode.SINGLE
        self._stack.setCurrentWidget(self.welcome_widget)

        # Connect image viewer signals
        self.image_viewer.next_image_requested.connect(self.next_image)
        self.image_viewer.prev_image_requested.connect(self.prev_image)
        self.image_viewer.zoom_changed.connect(lambda _: self.update_title())
        self.image_viewer.preview_size_requested.connect(
            self._request_refined_preview
        )
        self.image_viewer.full_resolution_requested.connect(
            self._request_full_resolution
        )
        self.image_viewer.toggle_mode_requested.connect(self.toggle_mode)
        self.image_viewer.page_scroll_requested.connect(
            self._scroll_single_page
        )

        # Connect scroll reader signals
        self.scroll_reader.visible_image_changed.connect(self._on_scroll_visible_changed)
        self.scroll_reader.zoom_changed.connect(lambda _: self.update_title())
        self.scroll_reader.toggle_mode_requested.connect(self.toggle_mode)
        self.scroll_reader.mode_single_requested.connect(lambda: self.set_mode(ViewerMode.SINGLE))
        self.scroll_reader.mode_scroll_requested.connect(lambda: self.set_mode(ViewerMode.SCROLL))

        # Floating bottom HUD overlay
        self._hud = ViewerHud(self)
        self._hud.prev_clicked.connect(self.prev_image)
        self._hud.next_clicked.connect(self.next_image)
        self._hud.jump_clicked.connect(self.goto_page_dialog)
        self._hud.mode_toggled.connect(self.toggle_mode)
        self._hud.zoom_in_clicked.connect(self._zoom_in)
        self._hud.zoom_out_clicked.connect(self._zoom_out)
        self._hud.zoom_reset_clicked.connect(self._reset_zoom)
        self._hud.fullscreen_toggled.connect(self.toggle_fullscreen)
        self._hud.comic_mode_selected.connect(self.set_comic_mode)
        self._hud.set_comic_mode(ComicMode.CUSTOM.value)
        self._hud.hide_immediately()

        # Keyboard event handler
        self._keyboard_handler = KeyboardEventHandler(
            on_next_image=self.next_image,
            on_prev_image=self.prev_image,
            on_first_image=self.first_image,
            on_last_image=self.last_image,
            on_zoom_in=self._zoom_in,
            on_zoom_out=self._zoom_out,
            on_reset_zoom=self._reset_zoom,
            on_mode_single=lambda: self.set_mode(ViewerMode.SINGLE),
            on_mode_scroll=lambda: self.set_mode(ViewerMode.SCROLL),
            on_toggle_mode=self.toggle_mode,
            on_fullscreen=self.toggle_fullscreen,
            on_exit_fullscreen=self._exit_fullscreen_if_active,
            on_exit=self.close,
            on_open_file=self.open_file_dialog,
            on_open_folder=self.open_folder_dialog,
            on_close_document=self.close_current,
            on_goto_page=self.goto_page_dialog,
            on_help=self.show_shortcuts_dialog,
            on_toggle_hud=self._hud.toggle_visibility,
        )

        # Enable drag-and-drop
        self.setAcceptDrops(True)
        self._stack.setAcceptDrops(True)
        self.welcome_widget.setAcceptDrops(True)
        self.image_viewer.setAcceptDrops(True)
        self.scroll_reader.setAcceptDrops(True)
        self.scroll_reader.viewport().setAcceptDrops(True)

        for widget in (
            self._stack,
            self.welcome_widget,
            self.image_viewer,
            self.scroll_reader,
            self.scroll_reader.viewport(),
        ):
            widget.installEventFilter(self)
            widget.setMouseTracking(True)
        self.setMouseTracking(True)

        # Native Menu Bar
        self.comic_mode = ComicMode.CUSTOM
        self._init_menu_bar()
        self._sync_comic_mode_state()

        # Image folder discovery / PDF state
        self.folder_path: Optional[str] = None
        self.pdf_path: Optional[str] = None
        self.image_list: List[str] = []
        self.current_index: int = -1
        self._requested_index: Optional[int] = None
        self._spread_pending_results: dict[str, DecodeResult] = {}
        self._request_generation = 0
        self._full_request_paths: set[str] = set()
        self._refine_request_keys: set[tuple[str, int, int]] = set()
        self._error_dialog: Optional[QMessageBox] = None
        self._single_scroll_transition: Optional[
            tuple[int, float, float, bool]
        ] = None

        initial_path = target_path or image_path
        if initial_path:
            self.load_image(initial_path)
        else:
            self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            self._stack.setCurrentWidget(self.welcome_widget)
            self.update_title()

    def set_mode(self, mode: ViewerMode) -> None:
        """Switch between Single Image mode and Scroll Reader mode, synchronizing current image."""
        if self.viewer_mode == mode:
            return

        self._single_scroll_transition = None
        self.viewer_mode = mode
        if mode == ViewerMode.SINGLE:
            # Sync active index from scroll reader to single image viewer
            idx = self.scroll_reader.current_visible_index()
            self.scroll_reader.release_render_cache()
            if 0 <= idx < len(self.image_list):
                self.current_index = idx
                self._request_index(idx, force=True)
            self._stack.setCurrentWidget(self.image_viewer)
            self.image_viewer.setFocus()
        elif mode == ViewerMode.SCROLL:
            # Sync active index from single image viewer to scroll reader
            self._request_generation += 1
            self._requested_index = None
            self._full_request_paths.clear()
            self._refine_request_keys.clear()
            self._spread_pending_results.clear()
            self._image_pipeline.cancel_queued(
                {
                    "current-preview",
                    "refined-preview",
                    "current-full",
                    "prefetch-preview",
                }
            )
            self.image_viewer.release_render_cache()
            self._stack.setCurrentWidget(self.scroll_reader)
            self.scroll_reader.setFocus()
            if 0 <= self.current_index < len(self.image_list):
                self.scroll_reader.scroll_to_index(self.current_index)

        self.update_title()
        self._sync_comic_mode_state()

    def toggle_mode(self) -> None:
        """Alternate between Single Image and Scroll Reader modes."""
        if self.viewer_mode == ViewerMode.SCROLL:
            self.set_mode(ViewerMode.SINGLE)
        else:
            self.set_mode(ViewerMode.SCROLL)

    def set_comic_mode(self, mode) -> None:
        """Apply one of the coordinated comic layout presets."""
        selected = mode if isinstance(mode, ComicMode) else ComicMode(mode)
        if selected == ComicMode.CUSTOM:
            self._sync_comic_mode_state()
            return

        presets = {
            ComicMode.COMICS: (True, False, True, True),
            ComicMode.MANGA: (True, True, True, True),
            ComicMode.WEBTOON: (False, False, False, False),
        }
        double_page, invert_order, page_spacing, detect_spreads = presets[selected]

        self._double_page_action.setChecked(double_page)
        self._invert_pages_action.setChecked(invert_order)
        self._page_spacing_action.setChecked(page_spacing)
        self._double_spread_action.setChecked(detect_spreads)

        self.scroll_reader.set_layout_options(
            double_page=double_page,
            invert_page_order=invert_order,
            page_spacing=page_spacing,
            detect_double_spreads=detect_spreads,
        )
        self.image_viewer.set_layout_options(
            double_page=double_page,
            invert_page_order=invert_order,
            page_spacing=page_spacing,
        )
        if selected == ComicMode.WEBTOON:
            self.scroll_reader.reset_zoom()
            self.set_mode(ViewerMode.SCROLL)

        self._sync_comic_mode_state()
        if self.viewer_mode == ViewerMode.SINGLE and self.image_list and self.current_index >= 0:
            self._request_index(self.current_index, force=True)

    def _resolve_matching_comic_mode(self) -> ComicMode:
        """Determine which ComicMode matches the currently active layout and viewer settings."""
        if not hasattr(self, "_double_page_action"):
            return ComicMode.CUSTOM

        dp = self._double_page_action.isChecked()
        inv = self._invert_pages_action.isChecked()
        sp = self._page_spacing_action.isChecked()
        ds = self._double_spread_action.isChecked()
        is_scroll = (self.viewer_mode == ViewerMode.SCROLL)

        # Comic Mode: Dual page, No change in mode. Activate Spacing and Double Spread, disable invert
        if dp and not inv and sp and ds:
            return ComicMode.COMICS

        # Manga Mode: Dual Page. No change in mode. Activate Spacing and Double Spread, enable invert
        if dp and inv and sp and ds:
            return ComicMode.MANGA

        # Webtoon: Scroll, disable spacing, disable the rest.
        if is_scroll and not dp and not inv and not sp and not ds:
            return ComicMode.WEBTOON

        return ComicMode.CUSTOM

    def _sync_comic_mode_state(self) -> None:
        """Synchronize comic_mode property, menu checkmarks, and HUD overlay with current config."""
        matched = self._resolve_matching_comic_mode()
        self.comic_mode = matched

        if hasattr(self, "_comic_mode_group") and hasattr(self, "_comic_actions"):
            self._comic_mode_group.setExclusive(False)
            for act_mode, action in self._comic_actions.items():
                action.setChecked(act_mode == matched)
            self._comic_mode_group.setExclusive(True)

        if hasattr(self, "_hud"):
            self._hud.set_comic_mode(matched.value)
            self._hud.reposition(self.width(), self.height())

    def _apply_custom_layout_options(self) -> None:
        """Apply individually selected View options and coordinate with matching preset."""
        dp = self._double_page_action.isChecked()
        inv = self._invert_pages_action.isChecked()
        sp = self._page_spacing_action.isChecked()
        ds = self._double_spread_action.isChecked()

        self.scroll_reader.set_layout_options(
            double_page=dp,
            invert_page_order=inv,
            page_spacing=sp,
            detect_double_spreads=ds,
        )
        self.image_viewer.set_layout_options(
            double_page=dp,
            invert_page_order=inv,
            page_spacing=sp,
        )
        self._sync_comic_mode_state()
        if self.viewer_mode == ViewerMode.SINGLE and self.image_list and self.current_index >= 0:
            self._request_index(self.current_index, force=True)

    def _double_spread_indices(self) -> Set[int]:
        if not self._double_spread_action.isChecked() or not self.image_list:
            return set()
        widths_by_index = {
            index: self.scroll_reader._get_source_size(path).width()
            for index, path in enumerate(self.image_list)
        }
        widths = [width for width in widths_by_index.values() if width > 0]
        if not widths:
            return set()
        average_width = sum(widths) / len(widths)
        return {
            index
            for index, width in widths_by_index.items()
            if width > average_width * 1.5
        }

    def _compute_spreads(self) -> List[tuple[int, ...]]:
        if not self.image_list:
            return []
        if not self._double_page_action.isChecked():
            return [(i,) for i in range(len(self.image_list))]

        spreads: List[tuple[int, ...]] = []
        spread_indices = self._double_spread_indices()

        # Cover (index 0) is always alone
        spreads.append((0,))

        index = 1
        n = len(self.image_list)
        while index < n:
            if index in spread_indices:
                spreads.append((index,))
                index += 1
                continue

            next_index = index + 1
            can_pair = (
                next_index < n
                and next_index not in spread_indices
            )
            if not can_pair:
                spreads.append((index,))
                index += 1
                continue

            spreads.append((index, next_index))
            index += 2

        return spreads

    def _get_spread_for_index(self, index: int) -> tuple[int, ...]:
        if not (0 <= index < len(self.image_list)):
            return ()
        for spread in self._compute_spreads():
            if index in spread:
                return spread
        return (index,)

    def _on_scroll_visible_changed(self, index: int) -> None:
        """Update current index and title when scrolling in Scroll Reader mode."""
        if self.viewer_mode == ViewerMode.SCROLL and 0 <= index < len(self.image_list):
            self.current_index = index
            self.update_title()

    def _zoom_in(self) -> None:
        self.image_viewer.zoom_in()
        self.scroll_reader.zoom_in()

    def _zoom_out(self) -> None:
        self.image_viewer.zoom_out()
        self.scroll_reader.zoom_out()

    def _reset_zoom(self) -> None:
        self.image_viewer.reset_view()
        self.scroll_reader.reset_zoom()

    def discover_images(
        self, folder_path: str, initial_file: Optional[str] = None
    ) -> bool:
        """Scan a folder for supported images, sort them alphabetically, and open the target."""
        if self.pdf_path:
            self._image_pipeline.wait_for_idle()
            close_pdf_handler(self.pdf_path)
            self.pdf_path = None

        self.folder_path = os.path.abspath(folder_path)
        discovered = []

        if os.path.exists(self.folder_path) and os.path.isdir(self.folder_path):
            try:
                for entry in os.scandir(self.folder_path):
                    if entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in SUPPORTED_EXTENSIONS:
                            discovered.append(entry.path)
            except OSError as e:
                print(f"Error reading folder '{self.folder_path}': {e}", file=sys.stderr)

        self.image_list = sorted(discovered, key=natural_sort_key)

        requested_index = 0 if self.image_list else -1
        if initial_file:
            init_abs = os.path.abspath(initial_file)
            init_ext = os.path.splitext(init_abs)[1].lower()
            if (
                init_abs not in self.image_list
                and os.path.isfile(init_abs)
                and init_ext in SUPPORTED_EXTENSIONS
            ):
                self.image_list.append(init_abs)
                self.image_list.sort(key=natural_sort_key)

            try:
                requested_index = self.image_list.index(init_abs)
            except ValueError:
                requested_index = 0 if self.image_list else -1

        self.current_index = requested_index
        self._requested_index = None
        self._single_scroll_transition = None

        if self.image_list and requested_index >= 0:
            self.setMinimumSize(320, 180)
            self.setMaximumSize(16777215, 16777215)
            self.resize(self.VIEWER_WIDTH, self.VIEWER_HEIGHT)
            target_widget = (
                self.scroll_reader
                if self.viewer_mode == ViewerMode.SCROLL
                else self.image_viewer
            )
            self._stack.setCurrentWidget(target_widget)
            self.scroll_reader.set_images(self.image_list, start_index=requested_index)
            res = self._request_index(requested_index, force=True)
            self._hud.set_page_info(requested_index, len(self.image_list))
            self._hud.set_mode(self.viewer_mode == ViewerMode.SCROLL)
            self._hud.reposition(self.width(), self.height())
            self._hud.hide_immediately()
            return res
        else:
            self.image_viewer.clear()
            self.scroll_reader.clear()
            self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            self._stack.setCurrentWidget(self.welcome_widget)
            self._hud.hide_immediately()
            self.update_title()
            return False

    def open_pdf(self, pdf_path: str, start_page: int = 0) -> bool:
        """Open a PDF document, acquire all page URIs and sizes, and display in single page mode by default."""
        resolved = os.path.abspath(pdf_path)
        if not is_pdf_file(resolved):
            return False

        if self.pdf_path and self.pdf_path != resolved:
            self._image_pipeline.wait_for_idle()
            close_pdf_handler(self.pdf_path)

        try:
            handler = get_pdf_handler(resolved)
        except Exception as e:
            self._show_load_error(resolved, f"Could not open PDF:\n{e}")
            return False

        if handler.page_count <= 0:
            self.image_viewer.clear()
            self.scroll_reader.clear()
            self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            self._stack.setCurrentWidget(self.welcome_widget)
            self._hud.hide_immediately()
            self.update_title()
            return False

        self.pdf_path = resolved
        self.folder_path = os.path.dirname(resolved)
        self.image_list = [
            build_pdf_page_uri(resolved, i) for i in range(handler.page_count)
        ]

        # Unlock sizing for reading view
        self.setMinimumSize(320, 180)
        self.setMaximumSize(16777215, 16777215)
        self.resize(self.VIEWER_WIDTH, self.VIEWER_HEIGHT)

        # PDF documents open by default in single page mode
        self.viewer_mode = ViewerMode.SINGLE
        self._sync_comic_mode_state()
        self._stack.setCurrentWidget(self.image_viewer)

        requested_index = max(0, min(start_page, len(self.image_list) - 1))
        self.current_index = requested_index
        self._requested_index = None
        self._single_scroll_transition = None

        self.scroll_reader.set_images(self.image_list, start_index=requested_index)
        res = self._request_index(requested_index, force=True)
        self._hud.set_page_info(requested_index, len(self.image_list))
        self._hud.set_mode(False)
        self._hud.reposition(self.width(), self.height())
        self._hud.hide_immediately()
        return res

    def load_image(self, image_path: str) -> bool:
        """Load an image file, PDF document, or discover folder images."""
        resolved = os.path.abspath(image_path)
        if is_pdf_file(resolved):
            return self.open_pdf(resolved)
        if os.path.isdir(resolved):
            return self.discover_images(resolved)
        return self.discover_images(os.path.dirname(resolved), initial_file=resolved)

    def open_path(self, target_path: str) -> bool:
        """Open an image file, PDF file, or directory."""
        return self.load_image(target_path)

    def load_current_image(self) -> bool:
        """Asynchronously reload the selected or currently displayed image."""
        index = (
            self._requested_index
            if self._requested_index is not None
            else self.current_index
        )
        if not self.image_list or not (0 <= index < len(self.image_list)):
            self.image_viewer.clear()
            self.scroll_reader.clear()
            self.update_title()
            return False
        return self._request_index(index, force=True)

    def _display_name(self, path: str) -> str:
        """Format filename for title display, distinguishing PDF pages."""
        pdf_info = parse_pdf_page_uri(path)
        if pdf_info is not None:
            pdf_file, page_idx = pdf_info
            return f"{os.path.basename(pdf_file)} (Page {page_idx + 1})"
        return os.path.basename(path)

    def update_title(self):
        """Update window title with [X/Total] counter, filename, dimensions, and zoom."""
        if not self.image_list:
            self.setWindowTitle(f"{APP_NAME} - [0/0] No images found")
            if hasattr(self, "_hud"):
                self._hud.hide_immediately()
            return

        mode_tag = " [Scroll]" if self.viewer_mode == ViewerMode.SCROLL else ""

        if self._requested_index is not None:
            spread = (
                self._get_spread_for_index(self._requested_index)
                if self.viewer_mode == ViewerMode.SINGLE
                else (self._requested_index,)
            )
            spreads = self._compute_spreads() if self.viewer_mode == ViewerMode.SINGLE else []
            if len(spread) == 2:
                name1 = self._display_name(self.image_list[spread[0]])
                name2 = self._display_name(self.image_list[spread[1]])
                counter = f"[{spread[0] + 1}-{spread[1] + 1}/{len(self.image_list)}]"
                self.setWindowTitle(
                    f"{APP_NAME}{mode_tag} - {counter} Loading {name1} | {name2}…"
                )
                if hasattr(self, "_hud"):
                    pos = spreads.index(spread) if spread in spreads else 0
                    self._hud.set_page_info(
                        self._requested_index,
                        len(self.image_list),
                        can_prev=(pos > 0),
                        can_next=(pos < len(spreads) - 1),
                        display_label=f"Page {spread[0] + 1}-{spread[1] + 1} / {len(self.image_list)}",
                    )
            else:
                path = self.image_list[self._requested_index]
                filename = self._display_name(path)
                self.setWindowTitle(
                    f"{APP_NAME}{mode_tag} - [{self._requested_index + 1}/{len(self.image_list)}] "
                    f"Loading {filename}…"
                )
                if hasattr(self, "_hud"):
                    if spreads and spread in spreads:
                        pos = spreads.index(spread)
                        can_prev = (pos > 0)
                        can_next = (pos < len(spreads) - 1)
                    else:
                        can_prev = (self._requested_index > 0)
                        can_next = (self._requested_index < len(self.image_list) - 1)
                    self._hud.set_page_info(
                        self._requested_index,
                        len(self.image_list),
                        can_prev=can_prev,
                        can_next=can_next,
                    )
            return

        if not (0 <= self.current_index < len(self.image_list)):
            self.setWindowTitle(f"{APP_NAME} - [0/0] No image displayed")
            if hasattr(self, "_hud"):
                self._hud.hide_immediately()
            return

        spread = (
            self._get_spread_for_index(self.current_index)
            if self.viewer_mode == ViewerMode.SINGLE
            else (self.current_index,)
        )
        spreads = self._compute_spreads() if self.viewer_mode == ViewerMode.SINGLE else []

        if self.viewer_mode == ViewerMode.SCROLL:
            mode_tag = " [Scroll]"
            zoom_factor = self.scroll_reader.zoom_factor
        else:
            mode_tag = ""
            zoom_factor = self.image_viewer.zoom_factor

        zoom_pct = int(round(zoom_factor * 100))
        zoom_str = f" - {zoom_pct}%" if zoom_pct != 100 else ""

        if len(spread) == 2:
            path1 = self.image_list[spread[0]]
            path2 = self.image_list[spread[1]]
            name1 = self._display_name(path1)
            name2 = self._display_name(path2)
            sz1 = self.image_viewer.source_size
            sz2 = self.image_viewer.sec_source_size
            dim_str = ""
            if sz1.isValid() and sz2.isValid():
                dim_str = f" ({sz1.width()}x{sz1.height()} + {sz2.width()}x{sz2.height()})"
            elif sz1.isValid():
                dim_str = f" ({sz1.width()}x{sz1.height()})"
            counter = f"[{spread[0] + 1}-{spread[1] + 1}/{len(self.image_list)}]"
            self.setWindowTitle(
                f"{APP_NAME}{mode_tag} - {counter} {name1} | {name2}{dim_str}{zoom_str}"
            )
            if hasattr(self, "_hud"):
                pos = spreads.index(spread) if spread in spreads else 0
                self._hud.set_page_info(
                    self.current_index,
                    len(self.image_list),
                    can_prev=(pos > 0),
                    can_next=(pos < len(spreads) - 1),
                    display_label=f"Page {spread[0] + 1}-{spread[1] + 1} / {len(self.image_list)}",
                )
                self._hud.set_mode(False)
                self._hud.set_zoom(zoom_factor)
        else:
            path = self.image_list[self.current_index]
            filename = self._display_name(path)
            source_size = (
                self.scroll_reader._get_source_size(path)
                if self.viewer_mode == ViewerMode.SCROLL
                else self.image_viewer.source_size
            )
            dim_str = (
                f" ({source_size.width()}x{source_size.height()})"
                if source_size.isValid()
                else ""
            )
            self.setWindowTitle(
                f"{APP_NAME}{mode_tag} - [{self.current_index + 1}/{len(self.image_list)}] {filename}{dim_str}{zoom_str}"
            )
            if hasattr(self, "_hud"):
                if spreads and spread in spreads:
                    pos = spreads.index(spread)
                    can_prev = (pos > 0)
                    can_next = (pos < len(spreads) - 1)
                else:
                    can_prev = (self.current_index > 0)
                    can_next = (self.current_index < len(self.image_list) - 1)
                self._hud.set_page_info(
                    self.current_index,
                    len(self.image_list),
                    can_prev=can_prev,
                    can_next=can_next,
                )
                self._hud.set_mode(self.viewer_mode == ViewerMode.SCROLL)
                self._hud.set_zoom(zoom_factor)

    def next_image(self):
        """Navigate to next image or spread in alphabetical order."""
        if not self.image_list:
            return
        if self.viewer_mode == ViewerMode.SINGLE:
            spreads = self._compute_spreads()
            curr_spread = self._get_spread_for_index(self._effective_index())
            if curr_spread in spreads:
                pos = spreads.index(curr_spread)
                if pos < len(spreads) - 1:
                    self.go_to_index(spreads[pos + 1][0])
                return
        base_index = self._effective_index()
        if base_index < len(self.image_list) - 1:
            self.go_to_index(base_index + 1)

    def prev_image(self):
        """Navigate to previous image or spread in alphabetical order."""
        if not self.image_list:
            return
        if self.viewer_mode == ViewerMode.SINGLE:
            spreads = self._compute_spreads()
            curr_spread = self._get_spread_for_index(self._effective_index())
            if curr_spread in spreads:
                pos = spreads.index(curr_spread)
                if pos > 0:
                    self.go_to_index(spreads[pos - 1][0])
                return
        base_index = self._effective_index()
        if base_index > 0:
            self.go_to_index(base_index - 1)

    def _scroll_single_page(
        self, direction: int, zoom_factor: float, horizontal_ratio: float
    ) -> None:
        """Cross a page boundary while retaining the single-view scroll state."""
        if not self.image_list:
            return
        if self.viewer_mode == ViewerMode.SINGLE:
            spreads = self._compute_spreads()
            curr_spread = self._get_spread_for_index(self._effective_index())
            if curr_spread in spreads:
                pos = spreads.index(curr_spread)
                target_pos = pos + direction
                if not (0 <= target_pos < len(spreads)):
                    return
                target_index = spreads[target_pos][0]
            else:
                target_index = self._effective_index() + direction
                if not (0 <= target_index < len(self.image_list)):
                    return
        else:
            target_index = self._effective_index() + direction
            if not (0 <= target_index < len(self.image_list)):
                return
        self._single_scroll_transition = (
            target_index,
            zoom_factor,
            horizontal_ratio,
            direction > 0,
        )
        self.go_to_index(target_index)

    def first_image(self):
        """Navigate to the first image."""
        if self.image_list:
            self.go_to_index(0)

    def last_image(self):
        """Navigate to the last image or spread."""
        if not self.image_list:
            return
        if self.viewer_mode == ViewerMode.SINGLE:
            spreads = self._compute_spreads()
            if spreads:
                self.go_to_index(spreads[-1][0])
                return
        self.go_to_index(len(self.image_list) - 1)

    def go_to_index(self, index: int):
        """Request an image and commit the index only after decoding succeeds."""
        if not (0 <= index < len(self.image_list)):
            return
        if self.viewer_mode == ViewerMode.SINGLE:
            target_spread = self._get_spread_for_index(index)
            curr_spread = self._get_spread_for_index(self._effective_index())
            if target_spread == curr_spread and self._requested_index is None:
                return
            self._request_index(target_spread[0])
        else:
            if index != self._effective_index():
                self._request_index(index)

    def _effective_index(self) -> int:
        if self._requested_index is not None:
            return self._requested_index
        return self.current_index

    def _request_index(self, index: int, force: bool = False) -> bool:
        if not (0 <= index < len(self.image_list)):
            return False

        spread = (
            self._get_spread_for_index(index)
            if self.viewer_mode == ViewerMode.SINGLE
            else (index,)
        )
        base_index = spread[0] if spread else index
        if not force and base_index == self._effective_index():
            return False

        self._request_generation += 1
        self._requested_index = base_index
        self._spread_pending_results.clear()
        self._full_request_paths.clear()
        self._refine_request_keys.clear()
        self._image_pipeline.cancel_queued(
            {
                "current-preview",
                "refined-preview",
                "current-full",
                "prefetch-preview",
            }
        )
        self.image_viewer.release_full_resolution()
        self.update_title()

        bounds = self.image_viewer.preview_bounds()
        for idx in spread:
            self._image_pipeline.request_preview(
                self.image_list[idx],
                bounds,
                self._request_generation,
                purpose="current-preview",
                priority=2,
            )
        return True

    def _on_image_ready(self, result: DecodeResult) -> None:
        request = result.request
        if request.purpose == "prefetch-preview":
            return
        if request.request_id != self._request_generation:
            return

        if request.purpose == "current-preview":
            if self._requested_index is None:
                return
            spread = (
                self._get_spread_for_index(self._requested_index)
                if self.viewer_mode == ViewerMode.SINGLE
                else (self._requested_index,)
            )
            expected_paths = [self.image_list[i] for i in spread]
            if request.path not in expected_paths:
                return

            self._spread_pending_results[request.path] = result
            if not all(p in self._spread_pending_results for p in expected_paths):
                return

            accepted_index = self._requested_index
            self.current_index = accepted_index
            self._requested_index = None
            if self.viewer_mode == ViewerMode.SCROLL:
                self.scroll_reader.scroll_to_index(accepted_index)

            preserve_scroll = False
            if self._single_scroll_transition is not None:
                transition_index = self._single_scroll_transition[0]
                preserve_scroll = (
                    self.viewer_mode == ViewerMode.SINGLE
                    and transition_index == accepted_index
                )
                if not preserve_scroll:
                    self._single_scroll_transition = None

            if len(spread) == 2:
                res1 = self._spread_pending_results[expected_paths[0]]
                res2 = self._spread_pending_results[expected_paths[1]]
                pix1 = QPixmap.fromImage(res1.image)
                pix2 = QPixmap.fromImage(res2.image)
                self.image_viewer.set_spread_preview(
                    (pix1, res1.source_size, res1.request.path),
                    (pix2, res2.source_size, res2.request.path),
                    reset_view=not preserve_scroll,
                )
            else:
                res = self._spread_pending_results[expected_paths[0]]
                pix = QPixmap.fromImage(res.image)
                self.image_viewer.set_preview_pixmap(
                    pix,
                    res.source_size,
                    res.request.path,
                    reset_view=not preserve_scroll,
                )

            self._spread_pending_results.clear()

            if preserve_scroll:
                _, zoom_factor, horizontal_ratio, at_top = (
                    self._single_scroll_transition
                )
                self._single_scroll_transition = None
                self.image_viewer.restore_scroll_position(
                    zoom_factor, horizontal_ratio, at_top
                )
            self.update_title()
            for p in expected_paths:
                self.image_loaded.emit(p)
            self._prefetch_neighbours()
            return

        if not (0 <= self.current_index < len(self.image_list)):
            return
        spread = (
            self._get_spread_for_index(self.current_index)
            if self.viewer_mode == ViewerMode.SINGLE
            else (self.current_index,)
        )
        current_paths = {self.image_list[idx] for idx in spread}
        if request.path not in current_paths:
            return

        pixmap = QPixmap.fromImage(result.image)
        if request.purpose == "refined-preview":
            bounds = request.bounds
            if bounds is None:
                return
            key = (
                request.path,
                bounds.width(),
                bounds.height(),
            )
            self._refine_request_keys.discard(key)
            self.image_viewer.set_refined_preview_pixmap(pixmap, request.path)
        elif request.purpose == "current-full":
            self._full_request_paths.discard(request.path)
            if self.image_viewer.zoom_factor > 1.0:
                self.image_viewer.set_full_resolution_pixmap(pixmap, request.path)

    def _on_image_failed(self, result: DecodeResult) -> None:
        request = result.request
        if request.request_id != self._request_generation:
            return
        if request.purpose == "refined-preview":
            bounds = request.bounds
            if bounds is None:
                return
            key = (
                request.path,
                bounds.width(),
                bounds.height(),
            )
            self._refine_request_keys.discard(key)
            return
        if request.purpose == "current-full":
            self._full_request_paths.discard(request.path)
            return
        if request.purpose != "current-preview" or self._requested_index is None:
            return

        failed_path = request.path
        self._requested_index = None
        self._spread_pending_results.clear()
        self._single_scroll_transition = None
        if self.current_index < 0:
            self.image_viewer.clear()
        self.update_title()
        self.image_load_failed.emit(failed_path)
        self._show_load_error(failed_path, result.error)

    def _request_refined_preview(self, bounds: QSize) -> None:
        if not (0 <= self.current_index < len(self.image_list)):
            return
        spread = (
            self._get_spread_for_index(self.current_index)
            if self.viewer_mode == ViewerMode.SINGLE
            else (self.current_index,)
        )
        for idx in spread:
            path = self.image_list[idx]
            key = (path, bounds.width(), bounds.height())
            if key in self._refine_request_keys:
                continue
            self._refine_request_keys.add(key)
            self._image_pipeline.request_preview(
                path,
                bounds,
                self._request_generation,
                purpose="refined-preview",
                priority=1,
            )

    def _request_full_resolution(self) -> None:
        if self._full_request_paths:
            return
        if not (0 <= self.current_index < len(self.image_list)):
            return
        bounds = self.image_viewer.detail_bounds()
        if not bounds.isValid():
            return
        spread = (
            self._get_spread_for_index(self.current_index)
            if self.viewer_mode == ViewerMode.SINGLE
            else (self.current_index,)
        )
        self._full_request_paths = {self.image_list[idx] for idx in spread}
        for idx in spread:
            self._image_pipeline.request_preview(
                self.image_list[idx],
                bounds,
                self._request_generation,
                purpose="current-full",
                priority=1,
            )

    def _prefetch_neighbours(self) -> None:
        if not (0 <= self.current_index < len(self.image_list)):
            return
        if self.viewer_mode == ViewerMode.SINGLE:
            spreads = self._compute_spreads()
            curr_spread = self._get_spread_for_index(self.current_index)
            neighbour_indices = set(curr_spread)
            if curr_spread in spreads:
                pos = spreads.index(curr_spread)
                if pos > 0:
                    neighbour_indices.update(spreads[pos - 1])
                if pos < len(spreads) - 1:
                    neighbour_indices.update(spreads[pos + 1])
            current_spread_set = set(curr_spread)
        else:
            neighbour_indices = {
                index
                for index in (
                    self.current_index - 1,
                    self.current_index,
                    self.current_index + 1,
                )
                if 0 <= index < len(self.image_list)
            }
            current_spread_set = {self.current_index}
        retained_paths = {self.image_list[index] for index in neighbour_indices}
        self._image_pipeline.retain_preview_paths(retained_paths)
        bounds = self.image_viewer.preview_bounds()
        for index in sorted(neighbour_indices - current_spread_set):
            self._image_pipeline.request_preview(
                self.image_list[index],
                bounds,
                self._request_generation,
                purpose="prefetch-preview",
                priority=0,
            )

    def _show_load_error(self, path: str, detail: str) -> None:
        if self._error_dialog is not None:
            self._error_dialog.close()
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("Error Loading Image")
        dialog.setText(f"Could not load image:\n{path}")
        if detail:
            dialog.setInformativeText(detail)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.finished.connect(
            lambda _result, dialog=dialog: self._clear_error_dialog(dialog)
        )
        self._error_dialog = dialog
        dialog.open()

    def _clear_error_dialog(self, dialog: QMessageBox) -> None:
        if self._error_dialog is dialog:
            self._error_dialog = None

    def _init_menu_bar(self):
        menubar = self.menuBar()
        menubar.setStyleSheet(
            "QMenuBar { background-color: #222222; color: #e0e0e0; font-size: 13px; }"
            "QMenuBar::item { background: transparent; padding: 4px 10px; }"
            "QMenuBar::item:selected { background-color: #383838; color: #ffffff; }"
            "QMenu { background-color: #2b2b2b; color: #e0e0e0; border: 1px solid #444; }"
            "QMenu::item { padding: 6px 24px 6px 20px; }"
            "QMenu::item:selected { background-color: #4a90e2; color: #ffffff; }"
            "QMenu::separator { height: 1px; background-color: #3d3d3d; margin: 4px 0px; }"
        )

        # File Menu
        file_menu = menubar.addMenu("&File")

        open_file_action = QAction("&Open File...", self)
        open_file_action.setShortcut("Ctrl+O")
        open_file_action.triggered.connect(self.open_file_dialog)
        file_menu.addAction(open_file_action)

        open_folder_action = QAction("Open &Folder...", self)
        open_folder_action.setShortcut("Ctrl+Shift+O")
        open_folder_action.triggered.connect(self.open_folder_dialog)
        file_menu.addAction(open_folder_action)

        close_action = QAction("&Close Document", self)
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(self.close_current)
        file_menu.addAction(close_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View Menu
        view_menu = menubar.addMenu("&View")

        mode_single_action = QAction("Single &Page Mode", self)
        mode_single_action.setShortcut("1")
        mode_single_action.triggered.connect(lambda: self.set_mode(ViewerMode.SINGLE))
        view_menu.addAction(mode_single_action)

        mode_scroll_action = QAction("Continuous &Scroll Mode", self)
        mode_scroll_action.setShortcut("2")
        mode_scroll_action.triggered.connect(lambda: self.set_mode(ViewerMode.SCROLL))
        view_menu.addAction(mode_scroll_action)

        view_menu.addSeparator()

        self._double_page_action = QAction("Double Page", self)
        self._double_page_action.setCheckable(True)
        self._double_page_action.triggered.connect(self._apply_custom_layout_options)
        view_menu.addAction(self._double_page_action)

        self._invert_pages_action = QAction("Invert Pages Order", self)
        self._invert_pages_action.setCheckable(True)
        self._invert_pages_action.triggered.connect(self._apply_custom_layout_options)
        view_menu.addAction(self._invert_pages_action)

        self._page_spacing_action = QAction("Activate Page Spacing", self)
        self._page_spacing_action.setCheckable(True)
        self._page_spacing_action.setChecked(True)
        self._page_spacing_action.triggered.connect(self._apply_custom_layout_options)
        view_menu.addAction(self._page_spacing_action)

        self._double_spread_action = QAction(
            "⚠ Default Double Spread Detection", self
        )
        self._double_spread_action.setCheckable(True)
        self._double_spread_action.setChecked(True)
        self._double_spread_action.setToolTip(
            "Show pages wider than 1.5× the folder average as a full row"
        )
        self._double_spread_action.triggered.connect(
            self._apply_custom_layout_options
        )
        view_menu.addAction(self._double_spread_action)

        view_menu.addSeparator()

        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut("Ctrl++")
        zoom_in_action.triggered.connect(self._zoom_in)
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut("Ctrl+-")
        zoom_out_action.triggered.connect(self._zoom_out)
        view_menu.addAction(zoom_out_action)

        zoom_reset_action = QAction("&Fit / Reset Zoom", self)
        zoom_reset_action.setShortcut("Ctrl+0")
        zoom_reset_action.triggered.connect(self._reset_zoom)
        view_menu.addAction(zoom_reset_action)

        view_menu.addSeparator()

        fs_action = QAction("Toggle &Fullscreen", self)
        fs_action.setShortcut("F11")
        fs_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fs_action)

        hud_action = QAction("Toggle &HUD", self)
        hud_action.setShortcut("H")
        hud_action.triggered.connect(self._hud.toggle_visibility)
        view_menu.addAction(hud_action)

        # Comic Modes Menu
        comic_menu = menubar.addMenu("&Comic Modes")
        self._comic_mode_group = QActionGroup(self)
        self._comic_mode_group.setExclusive(True)
        self._comic_actions = {}
        for label, mode in (
            ("Comics - Double Page, Left to Right", ComicMode.COMICS),
            ("Manga - Double Page, Right to Left", ComicMode.MANGA),
            ("Webtoon - Continuous, No Spacing", ComicMode.WEBTOON),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, selected=mode: (
                    self.set_comic_mode(selected) if checked else None
                )
            )
            self._comic_mode_group.addAction(action)
            self._comic_actions[mode] = action
            comic_menu.addAction(action)

        # Navigate Menu
        nav_menu = menubar.addMenu("&Navigate")

        next_action = QAction("&Next Page", self)
        next_action.setShortcut("Right")
        next_action.triggered.connect(self.next_image)
        nav_menu.addAction(next_action)

        prev_action = QAction("&Previous Page", self)
        prev_action.setShortcut("Left")
        prev_action.triggered.connect(self.prev_image)
        nav_menu.addAction(prev_action)

        first_action = QAction("&First Page", self)
        first_action.setShortcut("Home")
        first_action.triggered.connect(self.first_image)
        nav_menu.addAction(first_action)

        last_action = QAction("&Last Page", self)
        last_action.setShortcut("End")
        last_action.triggered.connect(self.last_image)
        nav_menu.addAction(last_action)

        nav_menu.addSeparator()

        goto_action = QAction("&Go to Page...", self)
        goto_action.setShortcut("Ctrl+G")
        goto_action.triggered.connect(self.goto_page_dialog)
        nav_menu.addAction(goto_action)

        # Help Menu
        help_menu = menubar.addMenu("&Help")

        shortcuts_action = QAction("Keyboard &Shortcuts", self)
        shortcuts_action.setShortcut("F1")
        shortcuts_action.triggered.connect(self.show_shortcuts_dialog)
        help_menu.addAction(shortcuts_action)

        about_action = QAction(f"&About {APP_NAME}", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def _can_accept_drag(self, event) -> bool:
        mime = event.mimeData()
        if not mime or not mime.hasUrls():
            return False
        for url in mime.urls():
            if url.isLocalFile():
                if self._is_supported_drag_path(url.toLocalFile()):
                    return True
        return False

    def _extract_valid_drag_path(self, event) -> Optional[str]:
        mime = event.mimeData()
        if not mime or not mime.hasUrls():
            return None
        for url in mime.urls():
            if url.isLocalFile():
                local_path = url.toLocalFile()
                if self._is_supported_drag_path(local_path):
                    return local_path
        return None

    def _is_supported_drag_path(self, path: str) -> bool:
        if not path or not os.path.exists(path):
            return False
        if os.path.isdir(path):
            return True
        if is_pdf_file(path):
            return True
        ext = os.path.splitext(path)[1].lower()
        return ext in SUPPORTED_EXTENSIONS

    def _set_drag_visual_hover(self, hover: bool):
        if hasattr(self, "welcome_widget"):
            self.welcome_widget.set_drag_hover(hover)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._can_accept_drag(event):
            event.acceptProposedAction()
            self._set_drag_visual_hover(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if self._can_accept_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._set_drag_visual_hover(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self._set_drag_visual_hover(False)
        path = self._extract_valid_drag_path(event)
        if path:
            event.acceptProposedAction()
            self.load_image(path)
        else:
            event.ignore()

    def eventFilter(self, watched, event: QEvent) -> bool:
        etype = event.type()
        if etype == QEvent.Type.DragEnter:
            if self._can_accept_drag(event):
                event.acceptProposedAction()
                self._set_drag_visual_hover(True)
                return True
            else:
                event.ignore()
                return True
        elif etype == QEvent.Type.DragMove:
            if self._can_accept_drag(event):
                event.acceptProposedAction()
                return True
            else:
                event.ignore()
                return True
        elif etype == QEvent.Type.DragLeave:
            self._set_drag_visual_hover(False)
            return True
        elif etype == QEvent.Type.Drop:
            self._set_drag_visual_hover(False)
            path = self._extract_valid_drag_path(event)
            if path:
                event.acceptProposedAction()
                self.load_image(path)
                return True
            else:
                event.ignore()
                return True
        elif etype == QEvent.Type.MouseMove:
            if self.image_list:
                local_pos = watched.mapTo(self, event.position().toPoint())
                self._hud.on_pointer_move(local_pos.y())
        return super().eventFilter(watched, event)

    def open_file_dialog(self):
        """Show open file dialog for images and PDF files."""
        filter_exts = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
        file_filter = (
            f"Supported Files (*.pdf {filter_exts});;"
            f"PDF Documents (*.pdf);;"
            f"Images ({filter_exts});;"
            f"All Files (*)"
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image or PDF Document",
            self.folder_path or "",
            file_filter,
        )
        if path:
            self.load_image(path)

    def open_folder_dialog(self):
        """Show open directory dialog to read a comic folder."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Open Comic Folder",
            self.folder_path or "",
        )
        if dir_path:
            self.discover_images(dir_path)

    def goto_page_dialog(self):
        """Prompt user for a page number to jump to."""
        if not self.image_list:
            return
        total = len(self.image_list)
        current = self.current_index + 1 if self.current_index >= 0 else 1
        page, ok = QInputDialog.getInt(
            self,
            "Go to Page",
            f"Enter page number (1 - {total}):",
            value=current,
            min=1,
            max=total,
        )
        if ok:
            target_idx = page - 1
            if self.viewer_mode == ViewerMode.SCROLL:
                self.scroll_reader.scroll_to_index(target_idx)
                self.current_index = target_idx
                self.update_title()
                self._hud.set_page_info(target_idx, total)
            else:
                self.go_to_index(target_idx)

    def show_shortcuts_dialog(self):
        """Display the styled keyboard and mouse shortcuts reference."""
        dialog = ShortcutsDialog(self)
        dialog.exec()

    def show_about_dialog(self):
        """Display the custom project and technology overview."""
        dialog = AboutDialog(self)
        dialog.exec()

    def close_current(self):
        """Close current document or folder and return to welcome screen."""
        self.folder_path = None
        self.image_list = []
        self.current_index = -1
        self._requested_index = None
        self.image_viewer.clear()
        self.scroll_reader.clear()
        self._image_pipeline.wait_for_idle()
        if self.pdf_path:
            close_pdf_handler(self.pdf_path)
            self.pdf_path = None
        if self.isFullScreen() or self.isMaximized() or self.isMinimized():
            self.showNormal()
        self.menuBar().setVisible(True)
        self._hud.set_fullscreen(False)
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self._stack.setCurrentWidget(self.welcome_widget)
        self._hud.hide_immediately()
        self.update_title()

    def toggle_fullscreen(self):
        """Toggle fullscreen mode on and off."""
        if self.isFullScreen():
            self.showNormal()
            self.menuBar().setVisible(True)
            self._hud.set_fullscreen(False)
        else:
            self.showFullScreen()
            self.menuBar().setVisible(False)
            self._hud.set_fullscreen(True)
        self._hud.reposition(self.width(), self.height())

    def _exit_fullscreen_if_active(self):
        if self.isFullScreen():
            self.toggle_fullscreen()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._hud.reposition(self.width(), self.height())

    def leaveEvent(self, event):
        """Begin hiding the HUD when the pointer leaves the reader window."""
        if self.image_list:
            self._hud.on_pointer_move(-1)
        super().leaveEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard navigation and shortcuts."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if not self._keyboard_handler.handle_key_press(event):
            if self.viewer_mode == ViewerMode.SCROLL and self.image_list:
                self.scroll_reader.keyPressEvent(event)
            else:
                super().keyPressEvent(event)

    def shutdown(self) -> None:
        """Finish decoder work before releasing Qt and PDFium resources."""
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._image_pipeline.shutdown()
        if self.pdf_path:
            close_pdf_handler(self.pdf_path)
            self.pdf_path = None

    def closeEvent(self, event):
        """Clean up resources on window close."""
        self.shutdown()
        super().closeEvent(event)
