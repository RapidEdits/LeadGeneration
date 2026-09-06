"""WhatsAppProvider — the ChannelProvider implementation for live WhatsApp sends.

Slots into the same seam as SimulatedProvider/EmailProvider: the engine's
`_dispatch` resolves it via `get_provider("whatsapp", test_mode=False)` and calls
`.send()`. A failed send is transient (retry) — WhatsApp has no hard-bounce concept.
"""
from __future__ import annotations

from app.models.enums import MessageStatus
from app.services.channel_provider import ChannelProvider, OutboundMessage, SendResult
from app.services.whatsapp import client


class WhatsAppProvider(ChannelProvider):
    def send(self, msg: OutboundMessage) -> SendResult:
        if not msg.to_address:
            return SendResult(success=False, status=MessageStatus.failed, error="No WhatsApp number for lead")
        try:
            result = client.send(msg.to_address, msg.body or "")
        except client.WhatsAppServiceError as exc:
            return SendResult(success=False, status=MessageStatus.failed, error=str(exc))
        if not result.get("success"):
            return SendResult(success=False, status=MessageStatus.failed, error=result.get("error"))
        return SendResult(
            success=True, status=MessageStatus.sent,
            provider_message_id=result.get("id"),
        )
