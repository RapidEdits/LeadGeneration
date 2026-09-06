"""Translate a LeadFilter (spec §22) into SQLAlchemy conditions, safely."""
from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models.lead import Lead
from app.schemas.lead import FilterCondition, LeadFilter

# Only these columns may be filtered/sorted — prevents arbitrary attribute access.
_FILTERABLE = {
    "full_name": Lead.full_name,
    "first_name": Lead.first_name,
    "last_name": Lead.last_name,
    "title": Lead.title,
    "email": Lead.email,
    "phone": Lead.phone,
    "linkedin_url": Lead.linkedin_url,
    "location": Lead.location,
    "status": Lead.status,
    "campaign_status": Lead.campaign_status,
    "score": Lead.score,
    "company_id": Lead.company_id,
    "created_at": Lead.created_at,
    "updated_at": Lead.updated_at,
}

_SORTABLE = _FILTERABLE


def _condition(fc: FilterCondition) -> ColumnElement | None:
    col = _FILTERABLE.get(fc.field)
    if col is None:
        return None
    op, val = fc.op, fc.value
    if op == "eq":
        return col == val
    if op == "neq":
        return col != val
    if op == "contains":
        return col.ilike(f"%{val}%")
    if op == "starts_with":
        return col.ilike(f"{val}%")
    if op == "in":
        return col.in_(val if isinstance(val, list) else [val])
    if op == "gt":
        return col > val
    if op == "gte":
        return col >= val
    if op == "lt":
        return col < val
    if op == "lte":
        return col <= val
    if op == "is_null":
        return col.is_(None)
    if op == "not_null":
        return col.isnot(None)
    return None


def build_conditions(flt: LeadFilter) -> list[ColumnElement]:
    conds: list[ColumnElement] = []
    field_conds = [c for fc in flt.conditions if (c := _condition(fc)) is not None]
    if field_conds:
        conds.append(and_(*field_conds) if flt.match == "all" else or_(*field_conds))
    if flt.search:
        term = f"%{flt.search}%"
        conds.append(
            or_(
                Lead.full_name.ilike(term),
                Lead.email.ilike(term),
                Lead.title.ilike(term),
                Lead.location.ilike(term),
            )
        )
    return conds


def order_by(flt: LeadFilter):
    col = _SORTABLE.get(flt.sort_by, Lead.created_at)
    return col.asc() if flt.sort_dir == "asc" else col.desc()
