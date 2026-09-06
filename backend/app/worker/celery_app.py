"""Celery application for the campaign engine.

Shares the backend package (models/services/db), so the worker and API run the
exact same `can_send` gate and engine code. Beat fires the periodic tick that
advances due campaign members.
"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

celery_app = Celery(
    "leadgen",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    beat_schedule={
        "campaign-tick": {
            "task": "engine.tick",
            "schedule": 30.0,  # seconds; dev cadence. Production can widen this.
        },
        "inbound-poll": {
            "task": "inbound.poll",
            "schedule": 120.0,  # poll connected mailboxes for replies/bounces every 2 min.
        },
    },
)
