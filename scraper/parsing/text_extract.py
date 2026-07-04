"""Best-effort extraction of business facets from the company summary text.

Moneycontrol has no structured "Products & Services", "Major Clients" or
"Order Book" fields; when such information exists at all it is buried in the
About-the-Company prose. These heuristics pull out the sentences that mention
each topic. Consumers must treat the values as optional -- ``None`` simply
means the profile text does not talk about that topic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

_PRODUCT_HINTS = re.compile(
    r"\b(product|service|solution|platform|portfolio|offering|offers?|provides?|"
    r"develops?|specialis|specializ|segment)\b",
    re.IGNORECASE,
)
_CLIENT_HINTS = re.compile(
    r"\b(client|customer|serves?|caters?|Fortune\s*500)\b", re.IGNORECASE
)
_ORDER_BOOK_HINTS = re.compile(
    r"\b(order\s*book|order\s*backlog|deal\s*wins?|total\s*contract\s*value|TCV|"
    r"pipeline\s+of\s+orders)\b",
    re.IGNORECASE,
)

_MAX_FACET_LENGTH = 1200


@dataclass(frozen=True)
class BusinessFacets:
    """Sentences of the business summary grouped by topic (all optional)."""

    products_services: str | None
    major_clients: str | None
    order_book: str | None


def _collect(sentences: list[str], pattern: re.Pattern[str]) -> str | None:
    hits = [s.strip() for s in sentences if pattern.search(s)]
    if not hits:
        return None
    text = " ".join(hits)
    if len(text) > _MAX_FACET_LENGTH:
        text = text[: _MAX_FACET_LENGTH - 3].rstrip() + "..."
    return text


def extract_business_facets(business_summary: str | None) -> BusinessFacets:
    """Split the summary into sentences and bucket them per topic."""
    if not business_summary:
        return BusinessFacets(None, None, None)
    # Moneycontrol sometimes glues sentences with ".." -- normalise first.
    normalised = re.sub(r"\.{2,}", ". ", business_summary)
    sentences = _SENTENCE_SPLIT_RE.split(normalised)
    return BusinessFacets(
        products_services=_collect(sentences, _PRODUCT_HINTS),
        major_clients=_collect(sentences, _CLIENT_HINTS),
        order_book=_collect(sentences, _ORDER_BOOK_HINTS),
    )
