"""Optional CSV export (enabled with EXPORT_CSV=true).

Writes one UTF-8 (BOM) CSV per data family into a timestamped folder so the
files open correctly in Excel without an import wizard.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class CsvExporter:
    """Plain CSV mirror of the main export tables."""

    def __init__(self, export_dir: Path) -> None:
        self._export_dir = export_dir

    @staticmethod
    def _write(path: Path, rows: list[dict]) -> None:
        if not rows:
            return
        fieldnames = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def export(
        self,
        companies: list[dict],
        quarterly: list[dict],
        annual: list[dict],
        shareholding: list[dict],
    ) -> Path:
        """Write all CSV files; returns the output folder."""
        folder = self._export_dir / f"csv_{datetime.now():%Y%m%d_%H%M%S}"
        folder.mkdir(parents=True, exist_ok=True)
        self._write(folder / "companies.csv", companies)
        self._write(folder / "quarterly_results.csv", quarterly)
        self._write(folder / "annual_results.csv", annual)
        self._write(folder / "shareholding.csv", shareholding)
        logger.info("CSV files written to %s", folder)
        return folder
