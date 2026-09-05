"""Image Viewer widget and main window implementation using Qt6."""

import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QMessageBox
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt, QRect


class ImageViewerWidget(QWidget):
    """Custom QWidget that uses QPainter to dynamically draw and scale its image
    to fit the window while preserving aspect ratio, without storing duplicate
    scaled pixmaps in memory.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)  # Allows window to shrink freely without getting blocked
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True) # Allows external styling
        self.setStyleSheet("background-color: #1a1a1a;")
        self._pixmap = None
        self._image_path = None

    def set_pixmap(self, pixmap: QPixmap):
        """Store source pixmap and request repaint."""
        self._pixmap = pixmap
        self.update()

    def pixmap(self):
        """Return source unscaled pixmap."""
        return self._pixmap

    def load_image(self, file_path: str) -> bool:
        """Load image from disk into pixmap."""
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            return False
        self._image_path = file_path
        self.set_pixmap(pixmap)
        return True

    def clear(self):
        """Clear current image and repaint empty canvas."""
        self._pixmap = None
        self._image_path = None
        self.update()

    def target_rect(self) -> QRect:
        """Calculate the centered, aspect-ratio-fitted target rectangle within the widget bounds."""
        if self._pixmap is None or self._pixmap.isNull():
            return QRect()

        widget_size = self.size()
        if widget_size.width() <= 0 or widget_size.height() <= 0:
            return QRect()

        target_size = self._pixmap.size().scaled(
            widget_size, Qt.AspectRatioMode.KeepAspectRatio
        )
        x = (widget_size.width() - target_size.width()) // 2
        y = (widget_size.height() - target_size.height()) // 2
        return QRect(x, y, target_size.width(), target_size.height())

    def paintEvent(self, event):
        """Draw background and scale unscaled pixmap directly onto canvas via QPainter."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))

        if (
            self._pixmap is not None
            and not self._pixmap.isNull()
            and self.width() > 0
            and self.height() > 0
        ):
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            rect = self.target_rect()
            if not rect.isEmpty():
                painter.drawPixmap(rect, self._pixmap)


# Backwards compatibility alias
ScaledImageLabel = ImageViewerWidget


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

        # Image viewer as central widget (using QPainter)
        self.image_viewer = ImageViewerWidget(self)
        self.viewer = self.image_viewer
        self.image_label = self.image_viewer  # Backwards compatibility alias
        self.setCentralWidget(self.image_viewer)

        if image_path:
            self.load_image(image_path)

    def load_image(self, image_path: str):
        """Load an image and update the window title."""
        if not self.image_viewer.load_image(image_path):
            QMessageBox.critical(
                self,
                "Error Loading Image",
                f"Could not load image:\n{image_path}\n\nPlease check the file path and format.",
            )
            return False

        pixmap = self.image_viewer.pixmap()
        filename = os.path.basename(image_path)
        self.setWindowTitle(
            f"Qt Scroll Reader - {filename} ({pixmap.width()}x{pixmap.height()})"
        )
        return True

