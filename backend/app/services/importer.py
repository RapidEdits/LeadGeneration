"""CSV import (spec §42): column-mapping → dedup → suppression → insert."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import LeadStatus
from app.models.lead import Lead, LeadSource
from app.schemas.common import CSVImportMapping, CSVImportResult
from app.services import dedup
from app.services.suppression import is_suppressed

# Lead fields a CSV column may map onto.
IMPORTABLE_FIELDS = {
    "full_name", "first_name", "last_name", "title", "email",
    "phone", "linkedin_url", "location", "notes",
}


def import_csv(db: Session, workspace_id: str, mapping: CSVImportMapping) -> CSVImportResult:
    source = LeadSource(workspace_id=workspace_id, kind="csv", name=mapping.source_name,
                        meta={"columns": mapping.column_map})
    db.add(source)
    db.flush()

    # Existing leads for dedup comparison (workspace-scoped).
    existing = db.execute(
        select(Lead).where(Lead.workspace_id == workspace_id)
    ).scalars().all()

    created = duplicates = suppressed = 0
    errors: list[str] = []
    # Track keys created within this batch so intra-file dupes are caught too.
    staged: list[Lead] = []

    for i, row in enumerate(mapping.rows):
        try:
            data = _map_row(row, mapping.column_map)
            if not any(data.get(f) for f in ("email", "linkedin_url", "phone", "full_name")):
                errors.append(f"Row {i + 1}: no identifying field, skipped")
                continue

            candidate = Lead(workspace_id=workspace_id, source_id=source.id, **data)
            if candidate.full_name is None and (candidate.first_name or candidate.last_name):
                candidate.full_name = " ".join(
                    filter(None, [candidate.first_name, candidate.last_name])
                )

            if mapping.apply_suppression and candidate.email and is_suppressed(
                db, workspace_id, "email", candidate.email
            ):
                suppressed += 1
                continue

            if mapping.dedup and _matches_any(candidate, existing + staged):
                duplicates += 1
                continue

            db.add(candidate)
            candidate.status = LeadStatus.new
            staged.append(candidate)
            created += 1
        except Exception as exc:  # noqa: BLE001 — report row error, keep importing
            errors.append(f"Row {i + 1}: {exc}")

    db.flush()
    return CSVImportResult(
        created=created,
        duplicates_skipped=duplicates,
        suppressed_skipped=suppressed,
        errors=errors,
        source_id=source.id,
    )


def _map_row(row: dict, column_map: dict[str, str]) -> dict:
    out: dict = {}
    for col, field in column_map.items():
        if field in IMPORTABLE_FIELDS and col in row:
            val = row[col]
            if isinstance(val, str):
                val = val.strip()
            out[field] = val or None
    return out


def _matches_any(candidate: Lead, others: list[Lead]) -> bool:
    for other in others:
        matched, _ = dedup.is_duplicate(candidate, other)
        if matched:
            return True
    return False
