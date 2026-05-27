from __future__ import annotations

import re


def _canonical(name: str) -> str:
    """Lowercase and whitespace-normalize a name string."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _name_slug(name: str) -> str:
    """Return a hyphen-separated slug from a canonical name per D19."""
    cleaned = re.sub(r"[^a-z0-9\s]", "", _canonical(name))
    return re.sub(r"\s+", "-", cleaned.strip())


def stable_id(node_type: str, name: str) -> str:
    """Generate a stable node ID per D19: <type-prefix>-<name-slug>.

    type_prefix = node_type.lower() with non-alphanumeric characters stripped.
    name_slug   = canonical_name (lowercased, whitespace-normalized) with
                  spaces replaced by hyphens.
    """
    type_prefix = re.sub(r"[^a-z0-9]", "", node_type.lower())
    return f"{type_prefix}-{_name_slug(name)}"
