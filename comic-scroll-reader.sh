#!/usr/bin/env bash
SCRIPT_DIR="$(dirname "$0")"
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m comic_scroll_reader "$@"
