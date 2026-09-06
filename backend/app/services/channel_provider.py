"""ChannelProvider abstraction — the seam where real senders plug in.

Phase 2 ships a SimulatedProvider used for every channel (test mode): it performs
no real network send, returning a synthetic provider id and a `simulated` status.
Phases 3-6 drop in EmailProvider (Gmail/MS365/SMTP), the WhatsApp OpenWA provider,
and the LinkedIn assisted-workflow provider behind this same interface — the engine
and `can_send` gate above them do not change.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.enums import MessageStatus


@dataclass
class OutboundMessage:
    channel: str
    to_address: str | None
    subject: str | None
    body: str | None


@dataclass
class SendResult:
    success: bool
    status: MessageStatus
    provider_message_id: str | None = None
    error: str | None = None


class ChannelProvider(ABC):
    @abstractmethod
    def send(self, msg: OutboundMessage) -> SendResult: ...


class SimulatedProvider(ChannelProvider):
    """Test-mode provider — records a send without touching any real network."""

    def send(self, msg: OutboundMessage) -> SendResult:
        return SendResult(
            success=True,
            status=MessageStatus.simulated,
            provider_message_id=f"sim_{uuid.uuid4().hex[:16]}",
        )


class NotImplementedProvider(ChannelProvider):
    """Live provider not wired yet for this channel (outside test mode)."""

    def __init__(self, channel: str, phase: str):
        self.channel = channel
        self.phase = phase

    def send(self, msg: OutboundMessage) -> SendResult:
        return SendResult(
            success=False,
            status=MessageStatus.failed,
            error=f"Live {self.channel} sending is not available yet (lands in {self.phase}).",
        )


_LIVE_PHASE = {"email": "Phase 3", "linkedin": "Phase 5", "whatsapp": "Phase 6"}


def get_provider(channel: str, *, test_mode: bool) -> ChannelProvider:
    if test_mode:
        return SimulatedProvider()
    # Live WhatsApp goes through the OpenWA microservice (Phase 6). Imported lazily
    # to avoid a cycle (the provider imports this module for the base class).
    if channel == "whatsapp":
        from app.services.whatsapp.provider import WhatsAppProvider
        return WhatsAppProvider()
    return NotImplementedProvider(channel, _LIVE_PHASE.get(channel, "a later phase"))
