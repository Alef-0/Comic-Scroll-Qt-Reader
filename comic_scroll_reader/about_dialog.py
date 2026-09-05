"""Custom About dialog for Comic Scroll Reader."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .resources import APP_NAME


class AboutDialog(QDialog):
    """Present project details in a compact, purpose-built layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aboutDialog")
        self.setWindowTitle(f"About {APP_NAME}")
        self.setModal(True)
        self.setMinimumWidth(620)
        self._init_ui()

    @staticmethod
    def _technology_card(title: str, subtitle: str, description: str) -> QFrame:
        card = QFrame()
        card.setObjectName("technologyCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(3)

        title_label = QLabel(title, card)
        title_label.setObjectName("technologyTitle")
        subtitle_label = QLabel(subtitle, card)
        subtitle_label.setObjectName("technologySubtitle")
        description_label = QLabel(description, card)
        description_label.setObjectName("technologyDescription")
        description_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addSpacing(5)
        layout.addWidget(description_label)
        return card

    def _init_ui(self):
        self.setStyleSheet(
            "QDialog#aboutDialog { background-color: #17191f; color: #ffffff; }"
            "QFrame#heroPanel { background-color: #222630; border: none; border-radius: 14px; }"
            "QLabel#heroIcon { background-color: #8ab4f8; color: #11141a; border-radius: 24px; font-size: 24px; }"
            "QLabel#appTitle { color: #ffffff; font-size: 24px; font-weight: 700; }"
            "QLabel#appTagline { color: #aeb6c4; font-size: 13px; }"
            "QLabel#sectionTitle { color: #8ab4f8; font-size: 12px; font-weight: 700; letter-spacing: 1px; }"
            "QFrame#technologyCard { background-color: #22252d; border: none; border-radius: 10px; }"
            "QLabel#technologyTitle { color: #ffffff; font-size: 15px; font-weight: 700; }"
            "QLabel#technologySubtitle { color: #8ab4f8; font-size: 11px; font-weight: 600; }"
            "QLabel#technologyDescription { color: #b8bec9; font-size: 12px; }"
            "QLabel#featureText { color: #d5d8df; font-size: 12px; line-height: 145%; }"
            "QLabel#acknowledgements { color: #ffffff; font-size: 12px; }"
            "QPushButton#closeButton { background-color: #8ab4f8; color: #11141a; border: none; border-radius: 7px; padding: 8px 24px; font-size: 12px; font-weight: 700; }"
            "QPushButton#closeButton:hover { background-color: #a7c7fa; }"
            "QPushButton#closeButton:pressed { background-color: #6f9fe9; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(16)

        hero = QFrame(self)
        hero.setObjectName("heroPanel")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 18, 20, 18)
        hero_layout.setSpacing(14)

        icon = QLabel("📖", hero)
        icon.setObjectName("heroIcon")
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(icon)

        identity_layout = QVBoxLayout()
        identity_layout.setSpacing(2)
        title = QLabel(APP_NAME, hero)
        title.setObjectName("appTitle")
        tagline = QLabel(
            "A focused desktop reader for images, comic folders, and PDF documents.",
            hero,
        )
        tagline.setObjectName("appTagline")
        tagline.setWordWrap(True)
        identity_layout.addWidget(title)
        identity_layout.addWidget(tagline)
        hero_layout.addLayout(identity_layout, 1)
        root.addWidget(hero)

        stack_heading = QLabel("BUILT WITH", self)
        stack_heading.setObjectName("sectionTitle")
        root.addWidget(stack_heading)

        technology_layout = QHBoxLayout()
        technology_layout.setSpacing(10)
        technology_layout.addWidget(
            self._technology_card(
                "Python 3",
                "PROGRAMMING LANGUAGE",
                "The application logic, document handling, and reader behavior.",
            ),
            1,
        )
        technology_layout.addWidget(
            self._technology_card(
                "PyQt6",
                "DESKTOP INTERFACE",
                "Qt widgets, input handling, image decoding, and custom painting.",
            ),
            1,
        )
        technology_layout.addWidget(
            self._technology_card(
                "pypdfium2",
                "PDF ENGINE",
                "Fast, on-demand PDF page rendering powered by Google PDFium.",
            ),
            1,
        )
        root.addLayout(technology_layout)

        features_heading = QLabel("READER EXPERIENCE", self)
        features_heading.setObjectName("sectionTitle")
        root.addWidget(features_heading)

        features = QLabel(
            "<b>Single page</b> and <b>continuous scroll</b> reading &nbsp;•&nbsp; "
            "Drag and drop<br/>"
            "Anchored zoom and pan &nbsp;•&nbsp; Keyboard navigation &nbsp;•&nbsp; "
            "Memory-bounded PDF viewing",
            self,
        )
        features.setObjectName("featureText")
        features.setTextFormat(Qt.TextFormat.RichText)
        features.setWordWrap(True)
        root.addWidget(features)

        root.addSpacing(4)
        footer_layout = QHBoxLayout()
        acknowledgement = QLabel(
            "Vibe coded by Alef_0 through Gemini and ChatGPT", self
        )
        acknowledgement.setObjectName("acknowledgements")
        footer_layout.addWidget(acknowledgement)
        footer_layout.addStretch(1)

        close_button = QPushButton("Close", self)
        close_button.setObjectName("closeButton")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.accept)
        close_button.setDefault(True)
        footer_layout.addWidget(close_button)
        root.addLayout(footer_layout)
