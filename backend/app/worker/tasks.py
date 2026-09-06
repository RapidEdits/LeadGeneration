"""Celery tasks. Job lifecycle: queued → processing → completed/failed/retrying."""
from __future__ import annotations

import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.services import engine, inbound
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="engine.tick", bind=True, max_retries=3, default_retry_delay=30)
def run_tick(self):
    """Process all due campaign members. Fired by beat and on-demand after launch."""
    db = SessionLocal()
    try:
        outcomes = engine.tick(db)
        if outcomes:
            logger.info("tick processed: %s", outcomes)
        return outcomes
    except Exception as exc:  # noqa: BLE001
        logger.exception("tick failed")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(name="inbound.poll", bind=True, max_retries=2, default_retry_delay=60)
def poll_inbound(self):
    """Poll all connected email accounts for replies/bounces."""
    if not settings.INBOUND_POLL_ENABLED:
        return {}
    db = SessionLocal()
    try:
        outcomes = inbound.poll_all(db)
        if outcomes:
            logger.info("inbound poll: %s", outcomes)
        return outcomes
    except Exception as exc:  # noqa: BLE001
        logger.exception("inbound poll failed")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(name="health.ping")
def ping() -> str:
    return "pong"
