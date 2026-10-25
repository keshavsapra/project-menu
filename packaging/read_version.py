"""Read the project version from pyproject.toml (single source of truth).

Works on Python 3.9+: uses `tomllib` (3.11+) when available and falls back
to a line-based parse of the `[project]` table otherwise, so the .deb build
smoke test can run on the whole CI matrix.
"""

import re
import sys
from pathlib import Path

pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
text = pyproject.read_text(encoding="utf-8")


def version() -> str:
    try:
        from tomllib import loads
    except ImportError:
        pass
    else:
        return loads(text)["project"]["version"]

    # Fallback for Python < 3.11: find `version = "..."` inside [project].
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if in_project:
            match = re.match(r'version\s*=\s*"([^"]+)"', stripped)
            if match:
                return match.group(1)

    sys.exit("packaging/read_version.py: no project version found in pyproject.toml")


print(version())
