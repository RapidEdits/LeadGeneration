"""WhatsApp subsystem (Phase 6).

Live WhatsApp sending runs through an internal Node microservice that mounts
OpenWA (unofficial WhatsApp Web automation). The backend never talks WhatsApp
directly — it calls the microservice over an internal shared-secret token:

    engine ──can_send──> WhatsAppProvider ──HTTP──> whatsapp-service ──> OpenWA

Inbound replies flow back the other way: the microservice POSTs each received
message to ``/api/v1/whatsapp/webhook``, which halts the lead's sequence exactly
like an email/LinkedIn reply. A session is a ``ConnectedAccount(type=whatsapp,
provider="openwa")``; no new tables are introduced for this phase.
"""
