from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, UploadFile, status

from app.api.deps import WorkspaceContext, require_role
from app.db.session import get_db
from app.models.enums import AuditAction, WorkspaceRole
from app.schemas.common import CSVImportMapping, CSVImportResult
from app.services import audit, importer
from fastapi import Depends as _Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/csv/preview")
async def preview_csv(file: UploadFile) -> dict:
    """Parse an uploaded CSV, return headers + a few sample rows for column mapping."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    headers = reader.fieldnames or []
    rows = list(reader)
    return {
        "headers": headers,
        "sample_rows": rows[:5],
        "total_rows": len(rows),
        "importable_fields": sorted(importer.IMPORTABLE_FIELDS),
    }


@router.post("/csv", response_model=CSVImportResult, status_code=status.HTTP_201_CREATED)
def import_csv(
    mapping: CSVImportMapping,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = _Depends(get_db),
) -> CSVImportResult:
    result = importer.import_csv(db, ctx.workspace_id, mapping)
    audit.record(db, action=AuditAction.import_csv, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="lead_source", entity_id=result.source_id,
                 data={"created": result.created, "duplicates": result.duplicates_skipped,
                       "suppressed": result.suppressed_skipped})
    db.commit()
    return result
