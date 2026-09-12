#!/usr/bin/env python3
"""Command-line entry point for Comic Scroll Reader."""

import argparse
import logging
import os
import signal
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

if __package__:
    from .core.resources import APP_ICON_PATH, APP_NAME, get_app_icon
    from .ui.main_window import MainWindow
else:
    from comic_scroll_reader.core.resources import APP_ICON_PATH, APP_NAME, get_app_icon
    from comic_scroll_reader.ui.main_window import MainWindow


def parse_arguments(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="comic-scroll-reader",
        description=(
            f"{APP_NAME} - View image folders, PDF documents, and CBZ/CBR "
            "comics in continuous-scroll or single-page mode."
        ),
    )
    parser.add_argument(
        "image_path",
        nargs="?",
        default=None,
        help="Optional path to an image, PDF, CBZ/CBR comic, or image directory to open",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print detailed image decoding and progressive sharpening messages",
    )
    return parser.parse_args(args)


def configure_logging(debug: bool) -> None:
    """Enable actionable pipeline diagnostics only when explicitly requested."""
    if not debug:
        return
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def is_desktop_file_installed(app_id: str = "comic-scroll-reader") -> bool:
    """Check if a corresponding .desktop file is installed in standard XDG application paths."""
    filename = f"{app_id}.desktop" if not app_id.endswith(".desktop") else app_id
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    data_dirs = (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    search_dirs = [os.path.join(data_home, "applications")] + [
        os.path.join(d, "applications") for d in data_dirs if d
    ]
    return any(os.path.isfile(os.path.join(d, filename)) for d in search_dirs)


def main():
    """Main execution entry point."""
    args = parse_arguments()
    env_debug = os.environ.get("COMIC_SCROLL_READER_DEBUG", "").casefold()
    configure_logging(args.debug or env_debug in {"1", "true", "yes", "on"})

    resolved_path = None
    if args.image_path:
        resolved_path = os.path.abspath(args.image_path)
        if not os.path.exists(resolved_path):
            print(f"Error: Path not found at '{resolved_path}'", file=sys.stderr)
            sys.exit(1)

    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_NAME)
    if is_desktop_file_installed("comic-scroll-reader"):
        QApplication.setDesktopFileName("comic-scroll-reader")
    app = QApplication(sys.argv)
    app.setWindowIcon(get_app_icon())

    # Enable terminal interrupt (Ctrl+C) handling
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    sigint_timer = QTimer()
    sigint_timer.setInterval(200)
    sigint_timer.timeout.connect(lambda: None)  # Periodically wake Python interpreter
    sigint_timer.start()

    window = MainWindow(target_path=resolved_path)
    app.aboutToQuit.connect(window.shutdown)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
