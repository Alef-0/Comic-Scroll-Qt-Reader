#!/usr/bin/env python3
import sys
import os
import argparse

try:
    from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QScrollArea, QMessageBox
    from PyQt5.QtGui import QPixmap
    from PyQt5.QtCore import Qt
except ImportError:
    from PySide2.QtWidgets import QApplication, QLabel, QMainWindow, QScrollArea, QMessageBox
    from PySide2.QtGui import QPixmap
    from PySide2.QtCore import Qt


class ImageViewer(QMainWindow):
    def __init__(self, image_path):
        super().__init__()
        self.setWindowTitle("Image Viewer")

        # Create QLabel to hold the image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)

        # Load image into QPixmap
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load image from:\n{image_path}\n\nCheck if the file format is supported."
            )
            sys.exit(1)

        self.image_label.setPixmap(pixmap)

        # Use QScrollArea so large images can be comfortably viewed
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.image_label)
        scroll_area.setWidgetResizable(True)
        self.setCentralWidget(scroll_area)

        # Set title with image info and initial window size
        filename = os.path.basename(image_path)
        self.setWindowTitle(f"Image Viewer - {filename} ({pixmap.width()}x{pixmap.height()})")

        # Sizing: adapt to image size up to sensible screen limits (1280x800)
        # width = min(pixmap.width() + 40, 1280)
        # height = min(pixmap.height() + 40, 800)
        self.resize(pixmap.size())


def main():
    parser = argparse.ArgumentParser(description="A minimal Qt image viewer.")
    parser.add_argument("image_path", help="Path to the image file to open")
    args = parser.parse_args()

    image_path = os.path.abspath(args.image_path)
    if not os.path.isfile(image_path):
        print(f"Error: File not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)
    viewer = ImageViewer(image_path)
    viewer.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
