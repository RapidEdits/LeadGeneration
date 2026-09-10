# Lead Generator

AI-powered lead discovery → enrichment → qualification → campaigns → multi-channel
outreach (Email / LinkedIn / WhatsApp) → reply handling → analytics, with
**responsible-outreach guardrails enforced server-side** (suppression, consent,
dedup, rate limits, human approval).

This repository is being built in phases. **Phase 1 (Foundation)** is complete: a
running, secure, multi-tenant shell with auth, database, navigation, and the
Leads / Companies / Settings core.

---

## Architecture

Monorepo with independently deployable services, orchestrated by `docker-compose`:

| Service | Stack | Purpose |
| --- | --- | --- |
| `frontend/` | Next.js 15 (App Router) + TS + Tailwind + shadcn-style UI | Web app |
| `backend/` | FastAPI + SQLAlchemy 2 + Alembic | REST API, OpenAPI, auth |
| `worker/` | Celery + Redis | Async jobs (outreach/enrichment/AI) — scaffold in P1 |
| `whatsapp-service/` | Node + Express (OpenWA in P6) | Internal messaging microservice |
| `postgres` | PostgreSQL 16 | Primary datastore |
| `redis` | Redis 7 | Celery broker / result backend |

### Key architectural rules
- **Centralized outbound authorization** — a single server-side
  `can_send(campaign, channel, lead)` gate (`backend/app/services/can_send.py`) is the
  *only* sanctioned path to any outbound action. Phase 1 enforces suppression; the
  full decision chain lands in Phase 2, enforced in the **worker**, not the UI.
- **Provider abstraction** — `AIService`, and (later) `EmailProvider` /
  `ChannelProvider` interfaces so models and channels plug in uniformly.
- **AIService** isolates every model call behind one contract. Default backend is
  **DeepSeek** (`DEEPSEEK_MODEL`, via an OpenAI-compatible endpoint — NVIDIA's
  inference API by default); Gemma (Google Generative Language API) is a drop-in
  fallback. Provider + model are env-driven (`AI_PROVIDER`); the shared
  `JsonModelService` base does defensive JSON extraction and always returns
  "unknown" rather than fabricating.
- **Workspace isolation** — every query is scoped to the caller's workspace; RBAC
  roles are owner / admin / sales / viewer.

---

## Prerequisites
- Docker Desktop (Docker Engine + Compose v2)
- Ports free: `3000` (frontend), `8000` (backend), `5432` (postgres), `6379`
  (redis), `3100` (whatsapp-service)

## Quick start

```bash
# 1. Create your env file and fill/replace secrets
cp .env.example .env
# Generate real secrets:
#   SECRET_KEY:     python -c "import secrets; print(secrets.token_urlsafe(48))"
#   ENCRYPTION_KEY: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. Bring up the whole stack
docker compose up -d --build

# 3. Apply database migrations (the backend also runs this on boot)
docker compose run --rm backend alembic upgrade head
```

Then open:
- Frontend: http://localhost:3000
- API docs (OpenAPI/Swagger): http://localhost:8000/docs
- Health: http://localhost:8000/health

Sign up to create your first user + workspace, then import a CSV of leads from the
**Leads** page.

## Running tests

Tests run against a dedicated `<db>_test` database (created automatically) so they
never touch dev data:

```bash
docker compose run --rm backend pytest
```

Covers: duplicate detection, suppression, advanced filtering, auth, and
workspace isolation.

## Database migrations

```bash
# Autogenerate a new migration after changing models
docker compose run --rm backend alembic revision --autogenerate -m "describe change"
# Apply
docker compose run --rm backend alembic upgrade head
```

---

## Security & configuration
- **No secrets are hardcoded.** All config comes from environment variables; see
  `.env.example` for every key. `.env` is git-ignored.
- Passwords hashed with bcrypt; JWT session tokens; connected-account credentials
  encrypted at rest with Fernet.
- Audit log records mutations; suppression list is global per workspace.

## ⚠️ WhatsApp / OpenWA notice
WhatsApp connectivity (Phase 6) uses **OpenWA**, an *unofficial* WhatsApp Web
automation library. It violates WhatsApp's Terms of Service and carries a real
risk of the connected number being **banned**. This is an accepted, informed
choice for early phases; the official Meta Cloud API can drop in behind the same
`ChannelProvider` interface later. The service is white-labeled — no OpenWA
branding is surfaced to end users.

---

## Phase roadmap
1. **Foundation** ✅ — auth, DB, nav, Leads/Companies/Settings, dedup, suppression, import
2. **Campaign engine** ✅ — builder, channel switches, sequences, `can_send` gate, state machine
3. **Email** ✅ — OAuth, send, tracking, replies, bounces, suppression, deliverability
4. **AI** ✅ — scoring, personalization, generation, reply classification, NL search, Copilot (DeepSeek / Gemma)
5. **LinkedIn** ✅ — assisted workflow + status tracking
6. **WhatsApp** ✅ — OpenWA service, delivery status, replies
7. **CRM** ✅ — pipeline Kanban, tasks, notes, meetings, lead timeline
8. **Analytics** ✅ — overview KPIs, funnel, outreach performance, AI insights
9. Production — security audit, rate limits, monitoring, tests, deployment, docs

> New here? Read **[docs/HOW-TO-GUIDE.md](docs/HOW-TO-GUIDE.md)** for a plain-English walkthrough.

## Product prospecting → campaign email

Open **Find leads** in the sidebar. Save your product name, overview, website,
ideal-customer keywords and locations (separate locations with semicolons).
Select a result limit from 1–100. Optional radius targeting takes a center latitude,
longitude and radius in kilometers.

**Search the web** uses Brave Search. An admin can save an encrypted workspace key
in the tab, or an operator can set `BRAVE_SEARCH_API_KEY` in `.env` and recreate the
backend/worker. Provider quota and usage charges apply; API documentation:
https://api-dashboard.search.brave.com/app/documentation/web-search.
**Supply websites** accepts up to 40 business URLs without a search key.

Discovery runs in the existing Celery worker and persists its progress and results.
It inspects at most 40 business sites, with up to two linked contact/about/location
pages per site, honors robots rules, bounds redirects/downloads, and blocks local,
private and reserved network destinations. The product website is read for context.
Only observed emails on the business's own domain are proposed. No email addresses
are guessed. Javascript-only sites, obfuscated emails and inaccessible pages may
produce no contacts. This is bounded public-web discovery, not exhaustive coverage
of the internet. Radius mode excludes sites without published geographic coordinates;
text-location mode shows matching page excerpts for manual review.

Results show keyword fit and source URLs, plus optional AI fit when the existing AI
service is configured. Public page text remains untrusted evidence, never an
instruction to the application. Keyword fit does not guarantee a good customer.
Review selected contacts, then save them to Leads, enroll them in a draft/paused
campaign, or create a new draft email campaign directly. Imports reuse existing
emails, honor suppression and preserve the source evidence. New campaigns start
in test mode with a 50-email daily limit. Review the subject/body in Campaigns,
connect a sending account in Settings, switch to live mode, and launch when ready.
The existing campaign engine handles bulk sends and sequence delays; normal waits
for daily limits or schedule windows no longer exhaust provider-failure retries.
Concurrent ticks lock campaigns to prevent overlapping processing.

**Inbox / Campaign mail** filters outbound messages and replies by campaign,
channel and status, with pagination, full bodies and message event history.
**Analytics → Email campaign insights** and each campaign's **Email insights** tab
show accepted sends, confirmed deliveries, unique opens/clicks/replies,
bounces, failures, queued/simulated messages and unsubscribes. Interactive daily
charts and an accessible data table cover 7/30/90/180-day windows.

Reports use the cohort of outbound emails created in the chosen UTC date range,
with engagement observed through now. A repeated open/click/reply counts once per
outbound email. Sent means the provider accepted the email; delivery is only counted
when explicitly confirmed. Opens/clicks can be affected by privacy features and
automated scanners. Tracking requires `PUBLIC_BASE_URL` to be a reachable HTTPS
address; inbound replies require a connected/pollable mailbox. Simulations and
failed/queued records are excluded from real-send metrics.

No new runtime dependency or database migration is required: product profiles and
bounded discovery runs reuse the existing workspace-scoped `lead_sources` JSONB
storage. Start/restart the backend, frontend, worker and beat after updating the code.

Verification (uses the isolated `_test` database, disables external AI and broker dispatch):
```bash
docker compose exec -T -e AI_PROVIDER=null -e CELERY_BROKER_URL=memory:// backend pytest -ra
docker compose run --rm --no-deps frontend npm run build
```
