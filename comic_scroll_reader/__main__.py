#!/usr/bin/env python3
"""Command-line entry point for Comic Scroll Reader."""

import argparse
import os
import signal
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

if __package__:
    from .main_window import MainWindow
    from .resources import APP_ICON_PATH, APP_NAME
else:
    from comic_scroll_reader.main_window import MainWindow
    from comic_scroll_reader.resources import APP_ICON_PATH, APP_NAME


def parse_arguments(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="comic-scroll-reader",
        description=f"{APP_NAME} - View image folders and PDF documents in continuous-scroll or single-page mode."
    )
    parser.add_argument(
        "image_path",
        nargs="?",
        default=None,
        help="Optional path to an image file, PDF file, or directory containing images to open",
    )
    return parser.parse_args(args)


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

    app_icon = QIcon(str(APP_ICON_PATH)) if APP_ICON_PATH.exists() else QIcon.fromTheme("comic-scroll-reader")
    app.setWindowIcon(app_icon)

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
