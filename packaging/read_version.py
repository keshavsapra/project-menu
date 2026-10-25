"""Read the project version from pyproject.toml (single source of truth)."""

from pathlib import Path
from tomllib import loads

pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
data = loads(pyproject.read_text(encoding="utf-8"))
print(data["project"]["version"])
