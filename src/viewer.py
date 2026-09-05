"""Image Viewer widget and main window implementation using Qt6."""

import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QMessageBox
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt


class ScaledImageLabel(QLabel):
    """QLabel that dynamically scales its image to fit the window while preserving aspect ratio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(1, 1)  # Allows window to shrink freely without getting blocked by pixmap size
        self.setStyleSheet("background-color: #1a1a1a;")
        self._pixmap = None

    def set_pixmap(self, pixmap: QPixmap):
        """Store original pixmap and update the displayed scaled pixmap."""
        self._pixmap = pixmap
        self._rescale()

    def pixmap(self):
        """Return original unscaled pixmap."""
        return self._pixmap

    def load_image(self, file_path: str) -> bool:
        """Load image from disk into pixmap."""
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            return False
        self.set_pixmap(pixmap)
        return True

    def resizeEvent(self, event):
        """Rescale image whenever the widget/window is resized."""
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        """Scale original pixmap to fit current bounds while keeping aspect ratio."""
        if (
            self._pixmap is not None
            and not self._pixmap.isNull()
            and self.width() > 0
            and self.height() > 0
        ):
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            super().setPixmap(scaled)


class MainWindow(QMainWindow):
    """Main window with default 1280x720 dimensions, resizable, displaying the image."""

    DEFAULT_WIDTH = 1280
    DEFAULT_HEIGHT = 720

    def __init__(self, image_path: str = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Qt Scroll Reader - Image Viewer")

        # Set default 1280x720 resizable window
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setMinimumSize(320, 180)

        # Image label as central widget (without QPainter)
        self.image_label = ScaledImageLabel(self)
        self.viewer = self.image_label
        self.setCentralWidget(self.image_label)

        if image_path:
            self.load_image(image_path)

    def load_image(self, image_path: str):
        """Load an image and update the window title."""
        if not self.image_label.load_image(image_path):
            QMessageBox.critical(
                self,
                "Error Loading Image",
                f"Could not load image:\n{image_path}\n\nPlease check the file path and format.",
            )
            return False

        pixmap = self.image_label.pixmap()
        filename = os.path.basename(image_path)
        self.setWindowTitle(
            f"Qt Scroll Reader - {filename} ({pixmap.width()}x{pixmap.height()})"
        )
        return True
