"""Isolated local UI fixture server. Run only against a database ending in _test.

AI_PROVIDER=null CELERY_BROKER_URL=memory:// uvicorn tests.preview_prospecting:app
Uses tests.conftest's dedicated database; never the application's main database.
"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.campaign import Campaign
from app.models.enums import Channel, MessageDirection, MessageEventType, MessageStatus
from app.models.message import Message, MessageEvent
from app.models.lead import LeadSource
from app.models.user import User
from tests.conftest import _TEST_URI, auth_headers, signup
from tests.test_prospecting import PAGE, PROFILE
from app.services import prospecting
from app.services.public_web import PublicWeb
from app.services.ai.base import NullAIService

database = create_engine(_TEST_URI)
assert database.url.database.endswith("_test")
Base.metadata.create_all(database)
Factory = sessionmaker(database)


def preview_db():
    with Factory() as db:
        yield db


app.dependency_overrides[get_db] = preview_db
with Factory() as db:
    existing = db.scalar(select(User.id).where(User.email == "preview@example.com"))
if not existing:
    with TestClient(app) as client:
        token, ws = signup(client, "preview@example.com", "Preview fixture — isolated test data")
        h = auth_headers(token, ws)
        client.put("/api/v1/prospecting/profile", headers=h, json=PROFILE)
        from unittest.mock import patch
        with patch("app.worker.tasks.discover_prospects.apply_async"), patch.object(PublicWeb, "fetch", lambda self, url: (url, PAGE)), patch.object(prospecting, "get_ai_service", lambda: NullAIService()):
            rid = client.post("/api/v1/prospecting/runs", headers=h, json={"mode": "websites", "websites": ["https://brightdental.com"]}).json()["id"]
            with Factory() as db:
                prospecting.execute_run(db, rid)
        cid = client.post("/api/v1/campaigns", headers=h, json={"name": "Dental clinics · Mumbai (fixture)", "test_mode": True}).json()["id"]
        with Factory() as db:
            for day in range(7):
                for i in range(2 + day):
                    m = Message(workspace_id=ws, campaign_id=cid, channel=Channel.email,
                        direction=MessageDirection.outbound, status=MessageStatus.sent, subject="Fixture email — scheduling for your clinic",
                        body="This is test fixture content. No message was sent.", to_address="fixture@example.com",
                        created_at=datetime.now(timezone.utc) - timedelta(days=day))
                    db.add(m); db.flush()
                    if i % 2 == 0:
                        db.add(MessageEvent(workspace_id=ws, message_id=m.id, type=MessageEventType.opened))
                    if i % 3 == 0:
                        db.add(MessageEvent(workspace_id=ws, message_id=m.id, type=MessageEventType.clicked))
                    if i == 0:
                        db.add(MessageEvent(workspace_id=ws, message_id=m.id, type=MessageEventType.replied))
            db.commit()
