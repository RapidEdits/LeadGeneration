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
- **AIService** isolates all Gemma calls (`AI_MODEL`, e.g. `gemma-4-31b-it`, via
  Google's Generative Language API). Model id is env-driven and swappable. Returns
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
4. **Gemma AI** ✅ — scoring, personalization, generation, reply classification, NL search, Copilot
5. LinkedIn — assisted workflow + status tracking
6. WhatsApp — OpenWA service, templates, delivery/read status, replies
7. CRM — pipeline Kanban, tasks, notes, meetings
8. Analytics — reports, funnel, attribution, AI insights
9. Production — security audit, rate limits, monitoring, tests, deployment, docs
