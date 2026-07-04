"""Configuration package: runtime settings and the NSE index registry."""

from scraper.config.settings import Settings, get_settings
from scraper.config.indices import IndexDefinition, DEFAULT_INDICES, get_index_registry

__all__ = [
    "Settings",
    "get_settings",
    "IndexDefinition",
    "DEFAULT_INDICES",
    "get_index_registry",
]
