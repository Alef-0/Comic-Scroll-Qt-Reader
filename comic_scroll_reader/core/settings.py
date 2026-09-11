"""Persistent application state stored under the user's .config directory."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger(__name__)

CONFIG_DIRECTORY_NAME = "comic-scroll-reader"
STATE_FILE_NAME = "state.json"
STATE_VERSION = 1


def config_directory() -> Path:
    """Return the settings directory, with an override for isolated tests."""
    override = os.environ.get("COMIC_SCROLL_READER_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / CONFIG_DIRECTORY_NAME


def state_file_path() -> Path:
    return config_directory() / STATE_FILE_NAME


def load_state() -> dict[str, Any]:
    """Load saved state, falling back safely when it is absent or malformed."""
    path = state_file_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        logger.warning("Could not load reader state from %s: %s", path, error)
        return {}

    if not isinstance(payload, dict):
        logger.warning("Ignoring reader state with an invalid root value: %s", path)
        return {}
    return payload


def save_state(state: dict[str, Any]) -> bool:
    """Atomically save state without leaving a partially written JSON file."""
    directory = config_directory()
    path = state_file_path()
    temporary_path: Optional[Path] = None
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = dict(state)
        payload["version"] = STATE_VERSION
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{STATE_FILE_NAME}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
        logger.debug("Reader state saved: %s", path)
        return True
    except OSError as error:
        logger.warning("Could not save reader state to %s: %s", path, error)
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        return False
