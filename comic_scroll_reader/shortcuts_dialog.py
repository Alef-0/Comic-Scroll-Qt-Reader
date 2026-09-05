"""Styled keyboard and mouse shortcuts dialog."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .resources import APP_NAME


class ShortcutsDialog(QDialog):
    """Present reader shortcuts using the application's card-based styling."""

    GROUPS = (
        (
            "READING",
            (
                ("1 / 2", "Single page / continuous scroll"),
                ("Right / Down / Space", "Next page"),
                ("Left / Up / Backspace", "Previous page"),
                ("Home / End", "First / last page"),
                ("Ctrl + G", "Go to a page"),
                ("Right click", "Toggle reader view"),
                ("Middle click", "Next page"),
            ),
        ),
        (
            "ZOOM AND MOVEMENT",
            (
                ("Ctrl + Wheel", "Zoom in or out"),
                ("Shift + Wheel", "Pan horizontally while zoomed"),
                ("Wheel", "Pan vertically; cross pages at an edge"),
                ("Ctrl + Plus / Minus", "Zoom in or out"),
                ("Ctrl + 0", "Reset zoom to fit"),
                ("Left drag", "Pan the image or viewport"),
                ("Double click", "Reset zoom and position"),
            ),
        ),
        (
            "FILES AND WINDOW",
            (
                ("Ctrl + O", "Open an image or PDF"),
                ("Ctrl + Shift + O", "Open a comic folder"),
                ("Ctrl + W", "Close the current document"),
                ("F11 / F", "Toggle fullscreen"),
                ("H", "Show or hide the bottom controls"),
                ("F1", "Open this shortcuts guide"),
                ("Esc", "Close the reader"),
            ),
        ),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("shortcutsDialog")
        self.setWindowTitle(f"Shortcuts - {APP_NAME}")
        self.setModal(True)
        self.setMinimumWidth(760)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet(
            "QDialog#shortcutsDialog { background-color: #17191f; color: #fff; }"
            "QFrame#heroPanel { background-color: #222630; border: none; border-radius: 14px; }"
            "QLabel#heroIcon { background-color: #8ab4f8; color: #11141a; border-radius: 24px; font-size: 24px; }"
            "QLabel#dialogTitle { color: #fff; font-size: 24px; font-weight: 700; }"
            "QLabel#dialogSubtitle { color: #aeb6c4; font-size: 13px; }"
            "QFrame#shortcutCard { background-color: #22252d; border: none; border-radius: 10px; }"
            "QLabel#sectionTitle { color: #8ab4f8; font-size: 12px; font-weight: 700; letter-spacing: 1px; }"
            "QLabel#keyLabel { background-color: #303641; color: #fff; border: 1px solid #454d5b; border-radius: 5px; padding: 4px 7px; font-size: 11px; font-weight: 700; }"
            "QLabel#descriptionLabel { color: #c7ccd5; font-size: 12px; }"
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

        icon = QLabel("⌨", hero)
        icon.setObjectName("heroIcon")
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(icon)

        identity = QVBoxLayout()
        identity.setSpacing(2)
        title = QLabel("Keyboard & Mouse Shortcuts", hero)
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "Everything you need for reading without leaving the page.", hero
        )
        subtitle.setObjectName("dialogSubtitle")
        identity.addWidget(title)
        identity.addWidget(subtitle)
        hero_layout.addLayout(identity, 1)
        root.addWidget(hero)

        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(12)
        for index, (group_title, shortcuts) in enumerate(self.GROUPS):
            column_span = 2 if index == len(self.GROUPS) - 1 else 1
            cards.addWidget(
                self._shortcut_card(group_title, shortcuts),
                index // 2,
                index % 2,
                1,
                column_span,
            )
        root.addLayout(cards)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close_button = QPushButton("Close", self)
        close_button.setObjectName("closeButton")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.accept)
        close_button.setDefault(True)
        footer.addWidget(close_button)
        root.addLayout(footer)

    def _shortcut_card(self, title: str, shortcuts) -> QFrame:
        card = QFrame(self)
        card.setObjectName("shortcutCard")
        layout = QGridLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(7)

        heading = QLabel(title, card)
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading, 0, 0, 1, 2)

        for row, (keys, description) in enumerate(shortcuts, start=1):
            key_label = QLabel(keys, card)
            key_label.setObjectName("keyLabel")
            key_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            description_label = QLabel(description, card)
            description_label.setObjectName("descriptionLabel")
            description_label.setWordWrap(True)
            layout.addWidget(key_label, row, 0)
            layout.addWidget(description_label, row, 1)

        layout.setColumnStretch(1, 1)
        return card
