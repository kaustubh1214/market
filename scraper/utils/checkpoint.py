"""Resume support.

A checkpoint file records which symbols finished during the current run. If
the process dies (network outage, Ctrl+C, crash) the next invocation skips
already-completed companies instead of re-scraping everything. The file is
deleted when a run completes normally.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FORMAT_VERSION = 1


class Checkpoint:
    """JSON-file backed set of completed symbols for an interrupted run."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._completed: set[str] = set()
        self._loaded_existing = False

    @property
    def resumed(self) -> bool:
        """True when a previous interrupted run was found and loaded."""
        return self._loaded_existing

    def load(self) -> None:
        """Load an existing checkpoint if present (tolerates corruption)."""
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if payload.get("version") == _FORMAT_VERSION:
                self._completed = set(payload.get("completed", []))
                self._loaded_existing = True
                logger.info(
                    "Resuming interrupted run: %d companies already done",
                    len(self._completed),
                )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Ignoring unreadable checkpoint %s: %s", self._path, exc)

    def is_done(self, symbol: str) -> bool:
        return symbol in self._completed

    def mark_done(self, symbol: str) -> None:
        """Record a finished symbol and persist immediately (crash safety)."""
        self._completed.add(symbol)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _FORMAT_VERSION, "completed": sorted(self._completed)}
        self._path.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    def clear(self) -> None:
        """Delete the checkpoint (called after a fully successful run)."""
        self._completed.clear()
        self._loaded_existing = False
        try:
            self._path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not delete checkpoint %s: %s", self._path, exc)
