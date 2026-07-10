from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..models import StateEvent


class AdapterError(ValueError):
    """Raised when an adapter cannot safely normalize its input."""


@dataclass(frozen=True)
class AdapterWarning:
    line_number: int
    source_event_id: str | None
    reason: str


@dataclass(frozen=True)
class AdaptedTrace:
    events: tuple[StateEvent, ...]
    source_record_count: int
    emitted_event_count: int
    skipped_record_count: int
    warnings: tuple[AdapterWarning, ...]


class RuntimeEventAdapter(Protocol):
    def read(self, source: Path) -> AdaptedTrace:
        """Return normalized events plus explicit warnings and skip counts."""
