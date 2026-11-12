"""Record an MCP-client-flagged issue to JSONL + the structured log.

This is the only sink the `report_issue` tool writes to. Two destinations:

1. Always: a single `ISSUE_REPORT <json>` log line. On Render or any other
   stdout-capturing host, this is the durable record of the report.
2. Best-effort: append the same JSON payload as one line to the file at
   `ISSUE_REPORT_PATH` (default `./data/issue_reports.jsonl`). On a developer
   laptop this is the source of truth; in production it may be ephemeral
   unless a persistent disk is attached.

If the file write fails the call still returns successfully; the structured
log line carries the full report so nothing is lost.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from shopify_meta import __version__

logger = logging.getLogger(__name__)

DEFAULT_PATH = "./data/issue_reports.jsonl"


REDACTED = "[REDACTED]"

# Keys whose values are dropped wherever they appear in the payload.
_SECRET_KEY = re.compile(
    r"token|secret|password|passwd|authorization|api[_-]?key|cookie|credential",
    re.IGNORECASE,
)
# Shopify credentials (shpat_/shpss_/shpca_/shppa_...) appearing inside text.
_SHOPIFY_TOKEN = re.compile(r"\bshp[a-z]{2}_[0-9a-fA-F]{16,}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


def _redact(value):
    """Best-effort scrub of credentials and email addresses before persisting.

    Reports carry model-supplied tool arguments and response excerpts, which can
    contain secrets or customer PII. Names/addresses can't be detected reliably;
    this covers credentials and emails.
    """
    if isinstance(value, dict):
        return {
            k: REDACTED if isinstance(k, str) and _SECRET_KEY.search(k) else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return _EMAIL.sub(REDACTED, _SHOPIFY_TOKEN.sub(REDACTED, value))
    return value


def _new_report_id() -> str:
    return "rpt_" + secrets.token_hex(4)


def record_issue(payload: dict) -> tuple[str, bool]:
    """Persist an issue report.

    Args:
        payload: Caller-supplied fields. Server-stamped metadata
            (`report_id`, `timestamp`, `server`, `server_version`,
            `python_version`) takes precedence over identically-named caller keys.

    Returns:
        `(report_id, wrote_to_file)` — `wrote_to_file` is False if the JSONL
        append failed (e.g. permission denied or ephemeral filesystem).
    """
    enriched = {
        **_redact(payload),
        "report_id": _new_report_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": "mcp-shopify-meta",
        "server_version": __version__,
        "python_version": sys.version.split()[0],
    }

    serialized = json.dumps(enriched, default=str)
    logger.info("ISSUE_REPORT %s", serialized)

    path = os.getenv("ISSUE_REPORT_PATH", DEFAULT_PATH)
    wrote = False
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(serialized + "\n")
        wrote = True
    except OSError as e:
        logger.warning("ISSUE_REPORT file write failed (%s): %s", path, e)

    return enriched["report_id"], wrote
