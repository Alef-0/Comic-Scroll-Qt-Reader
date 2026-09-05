#!/usr/bin/env bash
SCRIPT_DIR="$(dirname "$0")"
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi
exec "$PYTHON" "$SCRIPT_DIR/run_program.py" "$@"
