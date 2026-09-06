"""EmailProvider interface + normalized message/result objects."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EmailMessage:
    to_address: str
    subject: str
    html_body: str
    text_body: str
    from_address: str
    from_name: str | None = None
    reply_to: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class EmailSendResult:
    success: bool
    provider_message_id: str | None = None
    rfc_message_id: str | None = None
    error: str | None = None
    # True when the provider positively rejected the recipient (hard bounce at send time).
    hard_bounce: bool = False


class EmailProvider(ABC):
    """A connected email account able to send (and, where supported, be polled)."""

    #: short identifier: gmail | microsoft | smtp
    name: str = "email"

    @abstractmethod
    def send(self, msg: EmailMessage) -> EmailSendResult: ...

    def verify(self) -> tuple[bool, str | None]:
        """Cheap connectivity/credential check. Returns (ok, error)."""
        return True, None
