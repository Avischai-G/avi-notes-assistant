"""Load .env once, so every entry point (CLI, server, tests) sees the same config."""
import os
from pathlib import Path

for _line in (Path(__file__).parent.parent / ".env").read_text().splitlines() if (
        Path(__file__).parent.parent / ".env").exists() else []:
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
