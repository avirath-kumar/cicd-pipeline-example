"""Demo naming, namespaced by ``DEMO_OWNER`` so parallel runs do not collide.

``DEMO_OWNER=avi`` gives ``text2sql-agent-avi``; unset gives the original names.
"""

from __future__ import annotations

import os
import re

DATASET_BASE = "text2sql-agent"

# Names become DNS labels and LangSmith project names.
_OWNER_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def _resolve_owner() -> str:
    raw = (os.environ.get("DEMO_OWNER") or "").strip()
    if not raw:
        return ""
    slug = re.sub(r"[\s_]+", "-", raw.lower())
    if not _OWNER_RE.match(slug):
        raise ValueError(
            f"DEMO_OWNER={raw!r} is not usable in a name; use lowercase letters, "
            "digits and dashes, e.g. 'avi' or 'avi-kumar'."
        )
    return slug


OWNER = _resolve_owner()


def owned(base: str) -> str:
    """Suffix ``base`` with the owner slug, or return it unchanged."""
    return f"{base}-{OWNER}" if OWNER else base


DATASET_NAME = owned(DATASET_BASE)
EXPERIMENT_PREFIX_SQL = owned(f"{DATASET_BASE}-sql")
EXPERIMENT_PREFIX_E2E = owned(f"{DATASET_BASE}-e2e")
