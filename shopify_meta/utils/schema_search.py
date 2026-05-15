"""Ranked substring search over a SchemaIndex.

Ranking, best first:
1. exact case-insensitive name match
2. case-insensitive name prefix match
3. case-insensitive name substring match
4. case-insensitive description substring match

Within each tier, results are sorted by name ascending so output is stable.
"""

from __future__ import annotations

from .schema_loader import SchemaIndex, SearchEntry


def _rank(entry: SearchEntry, needle: str) -> int | None:
    """Return a rank (lower = better) or None if no match."""
    name_lower = entry.name.lower()
    if name_lower == needle:
        return 0
    if name_lower.startswith(needle):
        return 1
    if needle in name_lower:
        return 2
    if entry.description and needle in entry.description.lower():
        return 3
    return None


def search_schema_index(
    index: SchemaIndex,
    keyword: str,
    kinds: list[str] | None = None,
    limit: int = 25,
) -> dict:
    """Find matching schema entries, ranked.

    Returns:
        {
            "results": [{"name", "kind", "on_type", "description"}, ...],
            "total": int,        # total matches before limit
            "truncated": bool,   # True if total > len(results)
        }
    """
    if not keyword or not keyword.strip():
        raise ValueError("keyword must not be empty")

    needle = keyword.strip().lower()
    allowed = set(kinds) if kinds else None

    scored: list[tuple[int, str, SearchEntry]] = []
    for entry in index.search_entries:
        if allowed is not None and entry.kind not in allowed:
            continue
        rank = _rank(entry, needle)
        if rank is None:
            continue
        scored.append((rank, entry.name, entry))

    scored.sort(key=lambda x: (x[0], x[1]))

    total = len(scored)
    selected = scored[:limit]

    return {
        "results": [
            {
                "name": e.name,
                "kind": e.kind,
                "description": e.description,
                "on_type": e.on_type,
            }
            for _, _, e in selected
        ],
        "total": total,
        "truncated": total > len(selected),
    }
