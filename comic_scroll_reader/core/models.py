"""Shared reader modes, supported formats, and ordering helpers."""

import os
import re
from enum import Enum


class ViewerMode(Enum):
    SINGLE = "single"
    SCROLL = "scroll"


class ComicMode(Enum):
    DEFAULT = "default"
    COMICS = "comics"
    MANGA = "manga"
    WEBTOON = "webtoon"
    CUSTOM = "custom"


SUPPORTED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
    ".gif",
    ".tif",
    ".tiff",
    ".jfif",
    ".ico",
    ".svg",
    ".tga",
}


def natural_sort_key(file_path: str) -> list:
    """Sort strings containing numbers in human/natural alphabetical order."""
    filename = os.path.basename(file_path)
    return [
        int(token) if token.isdigit() else token.casefold()
        for token in re.split(r"(\d+)", filename)
    ]
