#!/usr/bin/env python3
"""Entry point for the Qt Scroll Reader application."""

import argparse
import os
import sys
from pathlib import Path

# Allow running directly via `python3 src/main.py <image>` or as a package `python3 -m src.main <image>`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.viewer import MainWindow, QApplication
else:
    from .viewer import MainWindow, QApplication


def parse_arguments(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Qt Scroll Reader - View an image scaled to fit the window while preserving aspect ratio."
    )
    parser.add_argument(
        "image_path",
        help="Path to the image file to open",
    )
    return parser.parse_args(args)


def main():
    """Main execution entry point."""
    args = parse_arguments()

    resolved_path = os.path.abspath(args.image_path)
    if not os.path.exists(resolved_path):
        print(f"Error: Image file not found at '{resolved_path}'", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(resolved_path):
        print(f"Error: Path '{resolved_path}' is not a file", file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)
    window = MainWindow(image_path=resolved_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
