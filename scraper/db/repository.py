"""Repositories: all SQL lives here.

The central design rule is *update only what changed*. Every upsert first
reads the existing row, diffs it field-by-field against the incoming data and
issues an UPDATE restricted to changed columns (or an INSERT when the row is
new). This keeps ``updated_at`` timestamps honest and makes reruns idempotent
-- running the scraper twice in a row produces zero writes the second time.

``None`` incoming values never overwrite existing data: a temporarily missing
field on Moneycontrol must not erase a previously scraped value.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone

from scraper.db.connection import Database
from scraper.models.company import (
    CompanyProfile,
    MarketData,
    PeriodResult,
    RunStats,
    ShareholdingEntry,
)
from scraper.utils.helpers import parse_db_timestamp, period_sort_key, utcnow_iso

logger = logging.getLogger(__name__)

_PROFILE_FIELDS = [f.name for f in dataclasses.fields(CompanyProfile)
                   if f.name != "nse_symbol"]
_MARKET_FIELDS = [f.name for f in dataclasses.fields(MarketData)
                  if f.name != "nse_symbol"]
_PERIOD_FIELDS = [f.name for f in dataclasses.fields(PeriodResult)
                  if f.name not in ("nse_symbol", "period_type", "period_label")]


class CompanyRepository:
    """Persistence for companies and their static/dynamic satellite tables."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # -- companies (static) -----------------------------------------------------

    def get_company_id(self, nse_symbol: str) -> int | None:
        row = self._db.fetch_one(
            "SELECT id FROM companies WHERE nse_symbol = ?", (nse_symbol,)
        )
        return row[0] if row else None

    def ensure_company(self, nse_symbol: str) -> int:
        """Return the company id, creating a stub row when unknown."""
        company_id = self.get_company_id(nse_symbol)
        if company_id is not None:
            return company_id
        now = utcnow_iso()
        cur = self._db.execute(
            "INSERT INTO companies (nse_symbol, created_at, updated_at) "
            "VALUES (?, ?, ?)",
            (nse_symbol, now, now),
        )
        self._db.commit()
        company_id = cur.lastrowid or self.get_company_id(nse_symbol)
        logger.debug("Created company row for %s (id=%s)", nse_symbol, company_id)
        return int(company_id)  # type: ignore[arg-type]

    def static_age_days(self, nse_symbol: str) -> float | None:
        """Days since the static profile was last refreshed (None = never)."""
        row = self._db.fetch_one(
            "SELECT static_updated_at, business_summary FROM companies "
            "WHERE nse_symbol = ?",
            (nse_symbol,),
        )
        if row is None or row[0] is None:
            return None
        # A row without its core static payload is treated as never scraped.
        if row[1] is None:
            return None
        stamp = parse_db_timestamp(row[0])
        if stamp is None:
            return None
        return (datetime.now(timezone.utc) - stamp).total_seconds() / 86400.0

    def upsert_profile(self, profile: CompanyProfile) -> list[str]:
        """Insert/update static data; returns the list of changed fields."""
        company_id = self.ensure_company(profile.nse_symbol)
        cols = ", ".join(_PROFILE_FIELDS)
        row = self._db.fetch_one(
            f"SELECT {cols} FROM companies WHERE id = ?", (company_id,)
        )
        existing = dict(zip(_PROFILE_FIELDS, row))  # type: ignore[arg-type]

        changed: dict[str, object] = {}
        for name in _PROFILE_FIELDS:
            new_value = getattr(profile, name)
            if new_value is not None and new_value != existing[name]:
                changed[name] = new_value

        now = utcnow_iso()
        assignments = [f"{name} = ?" for name in changed]
        assignments += ["static_updated_at = ?", "updated_at = ?"]
        params: list[object] = list(changed.values()) + [now, now, company_id]
        self._db.execute(
            f"UPDATE companies SET {', '.join(assignments)} WHERE id = ?", params
        )
        self._db.commit()
        if changed:
            logger.info(
                "%s: static fields updated: %s",
                profile.nse_symbol, ", ".join(sorted(changed)),
            )
        return sorted(changed)

    def touch_dynamic(self, nse_symbol: str) -> None:
        """Record that dynamic data was refreshed for this company."""
        now = utcnow_iso()
        self._db.execute(
            "UPDATE companies SET dynamic_updated_at = ?, updated_at = ? "
            "WHERE nse_symbol = ?",
            (now, now, nse_symbol),
        )
        self._db.commit()

    def set_index_membership(
        self, nse_symbol: str, memberships: list[tuple[str, str]]
    ) -> None:
        """Replace the set of (index_key, index_name) an equity belongs to."""
        company_id = self.ensure_company(nse_symbol)
        now = utcnow_iso()
        self._db.execute(
            "DELETE FROM company_indices WHERE company_id = ?", (company_id,)
        )
        for index_key, index_name in memberships:
            self._db.execute(
                "INSERT INTO company_indices (company_id, index_key, index_name, "
                "updated_at) VALUES (?, ?, ?, ?)",
                (company_id, index_key, index_name, now),
            )
        self._db.commit()

    # -- dynamic satellites -------------------------------------------------------

    def upsert_market_data(self, data: MarketData) -> list[str]:
        """Insert/update the market snapshot; returns changed field names."""
        company_id = self.ensure_company(data.nse_symbol)
        cols = ", ".join(_MARKET_FIELDS)
        row = self._db.fetch_one(
            f"SELECT {cols} FROM market_data WHERE company_id = ?", (company_id,)
        )
        now = utcnow_iso()
        if row is None:
            placeholders = ", ".join("?" for _ in _MARKET_FIELDS)
            values = [getattr(data, name) for name in _MARKET_FIELDS]
            self._db.execute(
                f"INSERT INTO market_data (company_id, {cols}, updated_at) "
                f"VALUES (?, {placeholders}, ?)",
                [company_id, *values, now],
            )
            self._db.commit()
            return list(_MARKET_FIELDS)

        existing = dict(zip(_MARKET_FIELDS, row))
        changed = {
            name: getattr(data, name)
            for name in _MARKET_FIELDS
            if getattr(data, name) is not None
            and getattr(data, name) != existing[name]
        }
        if changed:
            assignments = [f"{name} = ?" for name in changed] + ["updated_at = ?"]
            self._db.execute(
                f"UPDATE market_data SET {', '.join(assignments)} "
                "WHERE company_id = ?",
                [*changed.values(), now, company_id],
            )
            self._db.commit()
        return sorted(changed)

    def upsert_period_results(self, results: list[PeriodResult]) -> int:
        """Upsert quarterly/annual rows; returns number of rows written."""
        written = 0
        now = utcnow_iso()
        for res in results:
            company_id = self.ensure_company(res.nse_symbol)
            row = self._db.fetch_one(
                f"SELECT {', '.join(_PERIOD_FIELDS)} FROM period_results "
                "WHERE company_id = ? AND period_type = ? AND period_label = ?",
                (company_id, res.period_type, res.period_label),
            )
            if row is None:
                cols = ", ".join(_PERIOD_FIELDS)
                placeholders = ", ".join("?" for _ in _PERIOD_FIELDS)
                values = [getattr(res, name) for name in _PERIOD_FIELDS]
                self._db.execute(
                    f"INSERT INTO period_results (company_id, period_type, "
                    f"period_label, {cols}, updated_at) "
                    f"VALUES (?, ?, ?, {placeholders}, ?)",
                    [company_id, res.period_type, res.period_label, *values, now],
                )
                written += 1
                continue
            existing = dict(zip(_PERIOD_FIELDS, row))
            changed = {
                name: getattr(res, name)
                for name in _PERIOD_FIELDS
                if getattr(res, name) is not None
                and getattr(res, name) != existing[name]
            }
            if changed:
                assignments = [f"{n} = ?" for n in changed] + ["updated_at = ?"]
                self._db.execute(
                    f"UPDATE period_results SET {', '.join(assignments)} "
                    "WHERE company_id = ? AND period_type = ? AND period_label = ?",
                    [*changed.values(), now, company_id, res.period_type,
                     res.period_label],
                )
                written += 1
        self._db.commit()
        return written

    def replace_shareholding(
        self, nse_symbol: str, entries: list[ShareholdingEntry]
    ) -> None:
        """Replace the shareholding pattern snapshot for a company."""
        if not entries:
            return
        company_id = self.ensure_company(nse_symbol)
        now = utcnow_iso()
        self._db.execute(
            "DELETE FROM shareholding WHERE company_id = ?", (company_id,)
        )
        for entry in entries:
            self._db.execute(
                "INSERT INTO shareholding (company_id, category, percent, "
                "updated_at) VALUES (?, ?, ?, ?)",
                (company_id, entry.category, entry.percent, now),
            )
        self._db.commit()

    # -- reads for export -----------------------------------------------------------

    def fetch_companies_for_export(self, symbols: list[str]) -> list[dict]:
        """Full joined view of company + market data for the given symbols."""
        if not symbols:
            return []
        placeholders = ", ".join("?" for _ in symbols)
        profile_cols = ["nse_symbol", *_PROFILE_FIELDS,
                        "static_updated_at", "dynamic_updated_at"]
        market_cols = [f"m.{name}" for name in _MARKET_FIELDS]
        sql = (
            f"SELECT {', '.join('c.' + col for col in profile_cols)}, "
            f"{', '.join(market_cols)} "
            "FROM companies c LEFT JOIN market_data m ON m.company_id = c.id "
            f"WHERE c.nse_symbol IN ({placeholders}) ORDER BY c.company_name"
        )
        rows = self._db.fetch_all(sql, symbols)
        keys = profile_cols + _MARKET_FIELDS
        return [dict(zip(keys, row)) for row in rows]

    def fetch_period_results(
        self, symbols: list[str], period_type: str, limit_per_company: int | None = None
    ) -> list[dict]:
        """Period rows for the given symbols, newest first per company.

        Ordering comes from parsing the period label ("Mar '26" -> 2026-03),
        never from insertion order: rows inserted by later runs would
        otherwise appear in the wrong position.
        """
        if not symbols:
            return []
        placeholders = ", ".join("?" for _ in symbols)
        sql = (
            "SELECT c.nse_symbol, c.company_name, r.period_label, r.revenue, "
            "r.other_income, r.total_income, r.expenditure, r.interest, r.tax, "
            "r.net_profit, r.basic_eps, r.updated_at "
            "FROM period_results r JOIN companies c ON c.id = r.company_id "
            f"WHERE r.period_type = ? AND c.nse_symbol IN ({placeholders}) "
            "ORDER BY c.company_name"
        )
        rows = self._db.fetch_all(sql, [period_type, *symbols])
        keys = ["nse_symbol", "company_name", "period_label", "revenue",
                "other_income", "total_income", "expenditure", "interest",
                "tax", "net_profit", "basic_eps", "updated_at"]
        records = [dict(zip(keys, row)) for row in rows]
        records.sort(
            key=lambda r: (r["company_name"] or r["nse_symbol"],
                           tuple(-part for part in
                                 period_sort_key(r["period_label"]))),
        )
        if limit_per_company is None:
            return records
        limited: list[dict] = []
        per_company: dict[str, int] = {}
        for record in records:
            symbol = record["nse_symbol"]
            if per_company.get(symbol, 0) < limit_per_company:
                limited.append(record)
                per_company[symbol] = per_company.get(symbol, 0) + 1
        return limited

    def fetch_shareholding(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        placeholders = ", ".join("?" for _ in symbols)
        sql = (
            "SELECT c.nse_symbol, c.company_name, s.category, s.percent, "
            "s.updated_at FROM shareholding s "
            "JOIN companies c ON c.id = s.company_id "
            f"WHERE c.nse_symbol IN ({placeholders}) "
            "ORDER BY c.company_name, s.rowid"
        )
        keys = ["nse_symbol", "company_name", "category", "percent", "updated_at"]
        return [dict(zip(keys, row)) for row in self._db.fetch_all(sql, symbols)]

    def fetch_index_membership(self, symbols: list[str]) -> dict[str, list[str]]:
        """Map nse_symbol -> list of index names."""
        if not symbols:
            return {}
        placeholders = ", ".join("?" for _ in symbols)
        sql = (
            "SELECT c.nse_symbol, ci.index_name FROM company_indices ci "
            "JOIN companies c ON c.id = ci.company_id "
            f"WHERE c.nse_symbol IN ({placeholders}) ORDER BY ci.index_name"
        )
        result: dict[str, list[str]] = {}
        for symbol, index_name in self._db.fetch_all(sql, symbols):
            result.setdefault(symbol, []).append(index_name)
        return result


class RunRepository:
    """Persistence for run statistics and captured errors."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def start_run(self, stats: RunStats) -> int:
        started = stats.started_at.strftime("%Y-%m-%d %H:%M:%S")
        cur = self._db.execute(
            "INSERT INTO scrape_runs (started_at) VALUES (?)", (started,)
        )
        self._db.commit()
        if cur.lastrowid:  # psycopg2 has no usable lastrowid
            return int(cur.lastrowid)
        row = self._db.fetch_one(
            "SELECT MAX(id) FROM scrape_runs WHERE started_at = ?", (started,)
        )
        return int(row[0])  # type: ignore[index]

    def finish_run(self, run_id: int, stats: RunStats, notes: str = "") -> None:
        finished = (stats.finished_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        self._db.execute(
            "UPDATE scrape_runs SET finished_at = ?, indices_fetched = ?, "
            "constituents_seen = ?, it_companies = ?, companies_scraped = ?, "
            "companies_failed = ?, requests_made = ?, notes = ? WHERE id = ?",
            (finished, stats.indices_fetched, stats.constituents_seen,
             stats.it_companies, stats.companies_scraped, stats.companies_failed,
             stats.requests_made, notes, run_id),
        )
        for error in stats.errors:
            self._db.execute(
                "INSERT INTO scrape_errors (run_id, nse_symbol, company_name, "
                "stage, message, occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, error.nse_symbol, error.company_name, error.stage,
                 error.message,
                 error.occurred_at.strftime("%Y-%m-%d %H:%M:%S")),
            )
        self._db.commit()
