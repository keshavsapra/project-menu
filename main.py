#!/usr/bin/env python3
"""project-menu — cross-desktop, cross-distro Win+P style display switcher.

Entry point. See README.md for the full description, support matrix and
installation instructions.
"""

from __future__ import annotations

import os
import sys

# Make the source tree importable when run directly (e.g. `python3 main.py`).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
