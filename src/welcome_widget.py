"""Welcome / Empty State widget for Qt Scroll Reader."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class WelcomeWidget(QWidget):
    """Empty state widget shown when no file or folder is loaded.

    Provides a clean drop target for images, comic folders, and PDF documents,
    along with quick action buttons to open files or folders, an about/help button,
    and a cheat sheet of essential keyboard and mouse shortcuts.
    """

    open_file_requested = pyqtSignal()
    open_folder_requested = pyqtSignal()
    about_requested = pyqtSignal()

    CARD_WIDTH = 540

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_hover = False
        self._init_ui()

    def _init_ui(self):
        self.setObjectName("welcomeSurface")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#17191f"))
        self.setPalette(palette)
        self.setStyleSheet(
            "QWidget#welcomeSurface { background-color: #17191f; }"
            "QLabel { background: transparent; }"
            "QFrame#welcomeCard { border: none; }"
            "QFrame#heroPanel { background-color: #222630; border: none; border-radius: 14px; }"
            "QLabel#heroIcon { background-color: #8ab4f8; color: #11141a; border-radius: 25px; font-size: 25px; }"
            "QLabel#eyebrow { color: #8ab4f8; font-size: 10px; font-weight: 700; letter-spacing: 1px; }"
            "QLabel#title { color: #ffffff; font-size: 25px; font-weight: 700; }"
            "QLabel#subtitle { color: #b4bbc7; font-size: 13px; }"
            "QLabel#dropBadge { background-color: #303643; color: #9fc2fa; border: none; border-radius: 8px; padding: 6px 9px; font-size: 10px; font-weight: 700; }"
            "QPushButton#welcomeAction { background-color: #2a2e37; color: #ffffff; border: none; border-radius: 10px; padding: 9px 12px; font-size: 13px; font-weight: 600; }"
            "QPushButton#welcomeAction:hover { background-color: #353b48; }"
            "QPushButton#welcomeAction:pressed { background-color: #20232a; }"
            "QFrame#shortcutsPanel { background-color: #1d2027; border: none; border-radius: 10px; }"
            "QLabel#sectionTitle { color: #8ab4f8; font-size: 10px; font-weight: 700; letter-spacing: 1px; }"
            "QLabel#shortcutText { color: #aeb5c1; font-size: 11px; }"
            "QLabel#acknowledgements { color: #ffffff; font-size: 11px; }"
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 10)
        main_layout.setSpacing(9)

        # Borderless content surface; its background changes subtly during drag-over.
        self.card = QFrame(self)
        self.card.setObjectName("welcomeCard")
        self.card.setFixedWidth(self.CARD_WIDTH)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(11)

        # App identity and drop target.
        hero = QFrame(self.card)
        hero.setObjectName("heroPanel")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 15, 18, 15)
        hero_layout.setSpacing(13)

        icon_label = QLabel("📖", hero)
        icon_label.setObjectName("heroIcon")
        icon_label.setFixedSize(50, 50)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(icon_label)

        identity_layout = QVBoxLayout()
        identity_layout.setContentsMargins(0, 0, 0, 0)
        identity_layout.setSpacing(1)
        eyebrow_label = QLabel("WELCOME TO", hero)
        eyebrow_label.setObjectName("eyebrow")
        title_label = QLabel("Qt Scroll Reader", hero)
        title_label.setObjectName("title")
        subtitle_label = QLabel("Images, comic folders, and PDFs—your way.", hero)
        subtitle_label.setObjectName("subtitle")
        subtitle_label.setWordWrap(True)
        identity_layout.addWidget(eyebrow_label)
        identity_layout.addWidget(title_label)
        identity_layout.addWidget(subtitle_label)
        hero_layout.addLayout(identity_layout, 1)

        self.drop_badge = QLabel("DROP TO OPEN", hero)
        self.drop_badge.setObjectName("dropBadge")
        self.drop_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(self.drop_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        card_layout.addWidget(hero)

        # Primary actions.
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(9)

        self.btn_open_file = QPushButton("📄  Open File\nCtrl+O", self.card)
        self.btn_open_file.setObjectName("welcomeAction")
        self.btn_open_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_file.clicked.connect(self.open_file_requested.emit)
        btn_layout.addWidget(self.btn_open_file, 1)

        self.btn_open_folder = QPushButton("📁  Open Folder\nCtrl+Shift+O", self.card)
        self.btn_open_folder.setObjectName("welcomeAction")
        self.btn_open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_folder.clicked.connect(self.open_folder_requested.emit)
        btn_layout.addWidget(self.btn_open_folder, 1)

        self.btn_about = QPushButton("ℹ️  About\nProject & credits", self.card)
        self.btn_about.setObjectName("welcomeAction")
        self.btn_about.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_about.clicked.connect(self.about_requested.emit)
        btn_layout.addWidget(self.btn_about, 1)

        card_layout.addLayout(btn_layout)

        # Compact shortcut reference.
        shortcuts_panel = QFrame(self.card)
        shortcuts_panel.setObjectName("shortcutsPanel")
        shortcuts_layout = QVBoxLayout(shortcuts_panel)
        shortcuts_layout.setContentsMargins(15, 10, 15, 10)
        shortcuts_layout.setSpacing(4)

        shortcuts_title = QLabel("QUICK SHORTCUTS", shortcuts_panel)
        shortcuts_title.setObjectName("sectionTitle")
        shortcuts_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        shortcuts_layout.addWidget(shortcuts_title)

        tips_text = (
            "<b style='color: #ffffff;'>1 / 2</b> Reading mode &nbsp;•&nbsp; "
            "<b style='color: #ffffff;'>F11</b> Fullscreen &nbsp;•&nbsp; "
            "<b style='color: #ffffff;'>Esc</b> Close<br/>"
            "<b style='color: #ffffff;'>Drag</b> Pan &nbsp;•&nbsp; "
            "<b style='color: #ffffff;'>Ctrl+Wheel</b> Zoom &nbsp;•&nbsp; "
            "<b style='color: #ffffff;'>Arrows / Wheel</b> Navigate<br/>"
            "<b style='color: #ffffff;'>Ctrl+G</b> Go to page &nbsp;•&nbsp; "
            "<b style='color: #ffffff;'>F1</b> All shortcuts"
        )
        tips_label = QLabel(tips_text, shortcuts_panel)
        tips_label.setObjectName("shortcutText")
        tips_label.setTextFormat(Qt.TextFormat.RichText)
        tips_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        shortcuts_layout.addWidget(tips_label)

        card_layout.addWidget(shortcuts_panel)
        main_layout.addWidget(self.card, 1, Qt.AlignmentFlag.AlignHCenter)

        self.acknowledgements_label = QLabel(
            "Vibe coded by Alef_0 through Gemini and ChatGPT", self
        )
        self.acknowledgements_label.setObjectName("acknowledgements")
        self.acknowledgements_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(
            self.acknowledgements_label,
            0,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
        )
        self._update_card_style()

    def set_drag_hover(self, hover: bool):
        """Toggle visual drop-highlight state."""
        if self._drag_hover != hover:
            self._drag_hover = hover
            self._update_card_style()

    def _update_card_style(self):
        if self._drag_hover:
            self.card.setStyleSheet(
                "QFrame#welcomeCard {"
                "  background-color: #1d2a3b;"
                "  border: none;"
                "  border-radius: 14px;"
                "}"
            )
            self.drop_badge.setStyleSheet(
                "background-color: #8ab4f8; color: #11141a; border: none;"
                "border-radius: 8px; padding: 6px 9px; font-size: 10px; font-weight: 700;"
            )
        else:
            self.card.setStyleSheet(
                "QFrame#welcomeCard {"
                "  background-color: transparent;"
                "  border: none;"
                "  border-radius: 14px;"
                "}"
            )
            self.drop_badge.setStyleSheet("")
