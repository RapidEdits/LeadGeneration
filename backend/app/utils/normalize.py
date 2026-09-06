"""Normalization helpers used by dedup + suppression so comparisons are stable."""
from __future__ import annotations

import re

_non_digit = re.compile(r"\D+")


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    e = email.strip().lower()
    return e or None


def normalize_phone(phone: str | None) -> str | None:
    """Reduce to a comparable digit string, preserving a leading +."""
    if not phone:
        return None
    p = phone.strip()
    plus = p.startswith("+")
    digits = _non_digit.sub("", p)
    if not digits:
        return None
    return ("+" if plus else "") + digits


def normalize_linkedin(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.rstrip("/")
    return u or None


def normalize_name(name: str | None) -> str | None:
    if not name:
        return None
    n = re.sub(r"\s+", " ", name.strip().lower())
    return n or None
