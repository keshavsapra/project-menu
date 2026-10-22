"""Abstract interfaces and shared data types for project-menu.

The whole program is built around three pluggable abstractions:

* :class:`DisplayBackend`  -- reads/writes display configuration.
* :class:`HotkeyRegistrar` -- registers/unregisters the Super+P shortcut.
* :class:`PopupUI`         -- renders the "Project" menu overlay.

Backends, hotkey registrars and UIs are discovered at runtime (see
:mod:`backends.registry`, :mod:`hotkeys.registry` and :mod:`ui`) and selected
based on the detected environment (see :mod:`detect`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional


class DisplayMode(str, Enum):
    """The four Windows-like project modes."""

    INTERNAL = "internal"      # PC screen only
    DUPLICATE = "duplicate"    # Duplicate
    EXTEND = "extend"          # Extend
    EXTERNAL = "external"      # Second screen only


MODE_LABELS: dict[DisplayMode, str] = {
    DisplayMode.INTERNAL: "PC screen only",
    DisplayMode.DUPLICATE: "Duplicate",
    DisplayMode.EXTEND: "Extend",
    DisplayMode.EXTERNAL: "Second screen only",
}

# CLI friendly aliases so users can type `internal|external|extend|duplicate`.
MODE_ALIASES: dict[str, DisplayMode] = {
    "internal": DisplayMode.INTERNAL,
    "pc": DisplayMode.INTERNAL,
    "duplicate": DisplayMode.DUPLICATE,
    "clone": DisplayMode.DUPLICATE,
    "extend": DisplayMode.EXTEND,
    "external": DisplayMode.EXTERNAL,
    "second": DisplayMode.EXTERNAL,
}


class ExtendPosition(str, Enum):
    """Where the extended "second screen" is placed relative to the primary."""

    RIGHT = "right"
    LEFT = "left"
    ABOVE = "above"
    BELOW = "below"


POSITION_ALIASES: dict[str, ExtendPosition] = {
    "right": ExtendPosition.RIGHT,
    "left": ExtendPosition.LEFT,
    "above": ExtendPosition.ABOVE,
    "up": ExtendPosition.ABOVE,
    "below": ExtendPosition.BELOW,
    "down": ExtendPosition.BELOW,
}


@dataclass
class ModeInfo:
    """A single video mode / resolution."""

    width: int
    height: int
    refresh: float
    mode_id: Optional[str] = None  # backend-specific id (xrandr id, mutter id, ...)

    def __str__(self) -> str:
        r = f"{self.width}x{self.height}"
        if self.refresh:
            r += f"@{self.refresh:g}"
        return r

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass
class Output:
    """A physical display output as seen by a backend."""

    name: str
    description: str = ""
    connected: bool = True
    enabled: bool = False
    primary: bool = False
    builtin: bool = False
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    scale: float = 1.0
    current_mode: Optional[ModeInfo] = None
    modes: list[ModeInfo] = field(default_factory=list)

    @property
    def geometry(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    @property
    def is_active(self) -> bool:
        return self.connected and self.enabled

    def short(self) -> str:
        return f"{self.name} ({self.width}x{self.height}+{self.x}+{self.y})"


@dataclass
class ApplyResult:
    """Outcome of an ``apply`` / ``restore`` call."""

    ok: bool = True
    mode: Optional[DisplayMode] = None
    commands: list[str] = field(default_factory=list)  # what was / would be run
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class Selection:
    """A concrete user choice: a mode plus optional target/position."""

    mode: DisplayMode
    target_output: Optional[str] = None   # which output is the "second screen"
    position: ExtendPosition = ExtendPosition.RIGHT


class BackendError(Exception):
    """Base error for display backends."""


class UnsupportedBackendError(BackendError):
    """No backend is available for the detected environment."""


class BackendApplyError(BackendError):
    """A backend failed to apply a configuration."""


class DisplayBackend(ABC):
    """Abstract interface for manipulating display configuration."""

    name: str = "base"
    environments: tuple[str, ...] = ()
    priority: int = 100  # lower wins

    def __init__(self, env=None) -> None:
        self.env = env

    @classmethod
    def can_handle(cls, env) -> bool:
        """Return True if this backend is suitable for *env*."""
        return False

    def _normalize_selection(
        self,
        mode_or_selection: DisplayMode | Selection | str,
        target_output: Optional[str] = None,
        position: ExtendPosition | str = ExtendPosition.RIGHT,
    ) -> Selection:
        if isinstance(mode_or_selection, Selection):
            return mode_or_selection
        if isinstance(mode_or_selection, str):
            mode = MODE_ALIASES.get(mode_or_selection.lower(), DisplayMode(mode_or_selection.lower()))
        else:
            mode = mode_or_selection
        if isinstance(position, str):
            pos = POSITION_ALIASES.get(position.lower(), ExtendPosition(position.lower()))
        else:
            pos = position
        return Selection(mode=mode, target_output=target_output, position=pos)

    @abstractmethod
    def list_outputs(self) -> list[Output]:
        """Return all connected outputs (and their modes)."""

    @abstractmethod
    def get_current_mode(self) -> Optional[DisplayMode]:
        """Infer which of the four project modes is currently active."""

    @abstractmethod
    def plan(
        self,
        mode_or_selection: DisplayMode | Selection | str,
        target_output: Optional[str] = None,
        position: ExtendPosition | str = ExtendPosition.RIGHT,
    ) -> list[str]:
        """Return human-readable commands without executing anything."""

    @abstractmethod
    def apply(
        self,
        mode_or_selection: DisplayMode | Selection | str,
        target_output: Optional[str] = None,
        position: ExtendPosition | str = ExtendPosition.RIGHT,
    ) -> ApplyResult:
        """Apply selection or mode, capturing revert state for :meth:`restore`."""

    def snapshot(self) -> Any:
        """Capture the current configuration so it can be restored."""
        raise NotImplementedError

    def restore(self, snapshot: Any) -> ApplyResult:
        """Restore a previously captured configuration."""
        raise NotImplementedError


class HotkeyRegistrar(ABC):
    """Abstract interface for registering the Super+P global shortcut."""

    name: str = "base"

    @classmethod
    def can_handle(cls, env) -> bool:
        return False

    @abstractmethod
    def register(self, command: str) -> list[str]:
        """Register the hotkey; return the actions taken (for logging)."""

    @abstractmethod
    def unregister(self) -> list[str]:
        """Remove the hotkey; return the actions taken."""

    def instructions(self, command: str) -> str:
        """Human-readable manual instructions when auto-registration fails."""
        return ""


@dataclass
class UIContext:
    """Everything the popup needs to render and act."""

    backend: DisplayBackend
    options: list[tuple[DisplayMode, bool]]      # (mode, enabled)
    active_mode: Optional[DisplayMode]
    targets: list[Output]                        # candidates for "second screen"
    note: str = ""
    env: Any = None


class PopupUI(ABC):
    """Abstract interface for the popup selector."""

    @abstractmethod
    def run(self, context: UIContext) -> Optional[Selection]:
        """Show the popup, handle input, apply the choice, and return it."""
