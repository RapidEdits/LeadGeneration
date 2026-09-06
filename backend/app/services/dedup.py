"""Duplicate detection + merge (spec §5).

Deterministic, workspace-scoped, and unit-tested. Match precedence:
email > linkedin_url > phone > (full_name + company_id).
Pure functions where possible so tests don't need a DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from app.utils.normalize import (
    normalize_email,
    normalize_linkedin,
    normalize_name,
    normalize_phone,
)


class LeadLike(Protocol):
    id: str
    email: str | None
    linkedin_url: str | None
    phone: str | None
    full_name: str | None
    company_id: str | None


@dataclass(frozen=True)
class MatchKeys:
    email: str | None
    linkedin: str | None
    phone: str | None
    name_company: str | None


def compute_match_keys(lead: LeadLike) -> MatchKeys:
    name = normalize_name(getattr(lead, "full_name", None))
    company = getattr(lead, "company_id", None)
    name_company = f"{name}|{company}" if name and company else None
    return MatchKeys(
        email=normalize_email(getattr(lead, "email", None)),
        linkedin=normalize_linkedin(getattr(lead, "linkedin_url", None)),
        phone=normalize_phone(getattr(lead, "phone", None)),
        name_company=name_company,
    )


def is_duplicate(a: LeadLike, b: LeadLike) -> tuple[bool, str | None]:
    """Return (is_dup, match_type). Highest-confidence match wins."""
    ka, kb = compute_match_keys(a), compute_match_keys(b)
    if ka.email and ka.email == kb.email:
        return True, "email"
    if ka.linkedin and ka.linkedin == kb.linkedin:
        return True, "linkedin"
    if ka.phone and ka.phone == kb.phone:
        return True, "phone"
    if ka.name_company and ka.name_company == kb.name_company:
        return True, "name_company"
    return False, None


def find_duplicate_groups(leads: Iterable[LeadLike]) -> list[dict]:
    """Group leads that share any match key. Returns groups of size >= 2."""
    leads = list(leads)
    parent: dict[str, str] = {lead.id: lead.id for lead in leads}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        parent[find(x)] = find(y)

    # Bucket by each key type; union everything in a bucket.
    for key_attr in ("email", "linkedin", "phone", "name_company"):
        buckets: dict[str, list[str]] = {}
        for lead in leads:
            keys = compute_match_keys(lead)
            val = getattr(keys, key_attr)
            if val:
                buckets.setdefault(val, []).append(lead.id)
        for ids in buckets.values():
            for other in ids[1:]:
                union(ids[0], other)

    groups: dict[str, list[str]] = {}
    for lead in leads:
        groups.setdefault(find(lead.id), []).append(lead.id)

    result: list[dict] = []
    for root, ids in groups.items():
        if len(ids) >= 2:
            # Determine the strongest match type present in the group.
            match_type = _group_match_type([lead for lead in leads if lead.id in ids])
            result.append({"key": root, "match_type": match_type, "lead_ids": ids})
    return result


def _group_match_type(group: list[LeadLike]) -> str:
    keys = [compute_match_keys(g) for g in group]
    for attr, label in (("email", "email"), ("linkedin", "linkedin"),
                        ("phone", "phone"), ("name_company", "name_company")):
        seen: dict[str, int] = {}
        for k in keys:
            v = getattr(k, attr)
            if v:
                seen[v] = seen.get(v, 0) + 1
        if any(c >= 2 for c in seen.values()):
            return label
    return "unknown"


def merge_field_values(primary_val, dup_val):
    """Prefer the primary's non-empty value, else fall back to the duplicate's."""
    if primary_val not in (None, "", []):
        return primary_val
    return dup_val
