"""Shared test isolation for application-level configuration."""

import pytest


@pytest.fixture(autouse=True)
def isolate_reader_config(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Prevent window shutdown tests from writing to the user's real config."""
    monkeypatch.setenv(
        "COMIC_SCROLL_READER_CONFIG_DIR",
        str(tmp_path / "comic-scroll-reader"),
    )
