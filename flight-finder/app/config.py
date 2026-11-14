"""Loads settings from a .env file next to the app, if there is one.

Variables already set in the shell win over the file. Kept dependency-free on
purpose; the format is plain KEY=value lines, with # comments.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Optional[Path] = None) -> None:
    path = path or ENV_FILE
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value:
            os.environ.setdefault(key, value)
