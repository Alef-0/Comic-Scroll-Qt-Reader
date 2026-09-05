#!/usr/bin/env python3
"""Entry point for the Qt Scroll Reader application."""

import argparse
import os
import sys
from pathlib import Path

# Allow running directly via `python3 src/main.py <image_or_folder>` or as a package `python3 -m src.main <image_or_folder>`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.viewer import MainWindow, QApplication
else:
    from .viewer import MainWindow, QApplication


def parse_arguments(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Qt Scroll Reader - View images in a folder with keyboard/mouse navigation, zoom, and pan."
    )
    parser.add_argument(
        "image_path",
        help="Path to an image file or directory containing images to open",
    )
    return parser.parse_args(args)


def main():
    """Main execution entry point."""
    args = parse_arguments()

    resolved_path = os.path.abspath(args.image_path)
    if not os.path.exists(resolved_path):
        print(f"Error: Path not found at '{resolved_path}'", file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)
    window = MainWindow(target_path=resolved_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
