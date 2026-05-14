from __future__ import annotations

import hashlib
import re


def stable_id(prefix: str, *parts: object) -> str:
    payload = "|".join(str(part or "").strip().lower() for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def slugify(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized or "unknown"

