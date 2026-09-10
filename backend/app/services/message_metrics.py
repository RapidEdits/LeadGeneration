"""Shared definition of a real provider-accepted outbound message."""
from sqlalchemy import exists, or_, select

from app.models.enums import MessageEventType, MessageStatus, Provenance
from app.models.message import Message, MessageEvent


def real_message():
    return (Message.status != MessageStatus.simulated) & Message.meta["test_mode"].as_boolean().isnot(True)


def accepted_message():
    sent_event = exists(select(MessageEvent.id).where(
        MessageEvent.message_id == Message.id, MessageEvent.workspace_id == Message.workspace_id,
        MessageEvent.type == MessageEventType.sent, MessageEvent.provenance == Provenance.observed,
    ))
    return real_message() & or_(Message.status.in_([
        MessageStatus.sent, MessageStatus.delivered, MessageStatus.opened, MessageStatus.replied,
    ]), sent_event)
