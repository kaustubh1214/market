"""Registry of NSE indices the scraper knows how to fetch.

Each index maps to a constituents CSV published on the NSE archives host, e.g.
https://archives.nseindia.com/content/indices/ind_niftyitlist.csv

Adding a new index is a one-line change: add an :class:`IndexDefinition` to
``DEFAULT_INDICES`` (or list its key in the ``INDICES`` env var to restrict a
run to a subset). ``all_constituents_are_it`` short-circuits sector filtering
for indices that only contain IT companies (Nifty IT).
"""

from __future__ import annotations

from dataclasses import dataclass

NSE_INDEX_CSV_BASE = "https://archives.nseindia.com/content/indices/"


@dataclass(frozen=True)
class IndexDefinition:
    """A single NSE index and where to fetch its constituents."""

    key: str                       # stable identifier used in config / DB
    name: str                      # human-readable index name
    csv_filename: str              # file under NSE_INDEX_CSV_BASE
    all_constituents_are_it: bool = False

    @property
    def csv_url(self) -> str:
        return NSE_INDEX_CSV_BASE + self.csv_filename


DEFAULT_INDICES: list[IndexDefinition] = [
    IndexDefinition(
        key="nifty_it",
        name="Nifty IT",
        csv_filename="ind_niftyitlist.csv",
        all_constituents_are_it=True,
    ),
    IndexDefinition(
        key="nifty_midcap_150",
        name="Nifty Midcap 150",
        csv_filename="ind_niftymidcap150list.csv",
    ),
    IndexDefinition(
        key="nifty_midsmallcap_400",
        name="Nifty MidSmallcap 400",
        csv_filename="ind_niftymidsmallcap400list.csv",
    ),
    IndexDefinition(
        key="nifty_smallcap_250",
        name="Nifty Smallcap 250",
        csv_filename="ind_niftysmallcap250list.csv",
    ),
    IndexDefinition(
        key="nifty_largemidcap_250",
        name="Nifty LargeMidcap 250",
        csv_filename="ind_niftylargemidcap250list.csv",
    ),
    IndexDefinition(
        key="nifty_midcap_select",
        name="Nifty Midcap Select",
        csv_filename="ind_niftymidcapselect_list.csv",
    ),
]


def get_index_registry(selected_keys: list[str] | None = None) -> list[IndexDefinition]:
    """Return index definitions for a run.

    Args:
        selected_keys: optional subset of index keys (from config). Unknown
            keys raise ``KeyError`` so typos fail fast instead of silently
            scraping nothing.
    """
    if not selected_keys:
        return list(DEFAULT_INDICES)
    by_key = {ix.key: ix for ix in DEFAULT_INDICES}
    missing = [k for k in selected_keys if k not in by_key]
    if missing:
        raise KeyError(
            f"Unknown index key(s): {missing}. Known keys: {sorted(by_key)}"
        )
    return [by_key[k] for k in selected_keys]
