from __future__ import annotations
import json
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.campaign import Campaign, CampaignLead
from app.models.message import Message
from app.models.lead import Lead

db = SessionLocal()
now = datetime.now(timezone.utc)
print("NOW:", now.isoformat())

print("\n=== Active/paused campaigns ===")
for c in db.execute(select(Campaign).order_by(Campaign.created_at.desc())).scalars().all():
    print(f"- {c.name!r} state={c.state.value} test_mode={c.test_mode} channels={c.channels}")

print("\n=== Campaign leads (all) ===")
for m in db.execute(select(CampaignLead)).scalars().all():
    lead = db.get(Lead, m.lead_id)
    camp = db.get(Campaign, m.campaign_id)
    due = "DUE" if (m.next_action_at and m.next_action_at <= now) else ("future" if m.next_action_at else "-")
    print(f"- camp={camp.name!r}({camp.state.value}) lead={getattr(lead,'email',None)!r} "
          f"state={m.state.value} step={m.current_step} attempts={m.attempts} "
          f"reason={m.last_reason!r} next={m.next_action_at} [{due}]")

print("\n=== Last 8 messages ===")
for msg in db.execute(select(Message).order_by(Message.created_at.desc()).limit(8)).scalars().all():
    print(f"- {msg.created_at} ch={msg.channel.value} status={msg.status.value} to={msg.to_address!r} "
          f"pmid={msg.provider_message_id!r} meta={json.dumps(msg.meta) if msg.meta else msg.meta}")
db.close()
