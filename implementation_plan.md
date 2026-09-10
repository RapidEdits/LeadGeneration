# Product prospecting and campaign email reporting

Use existing LeadSource JSON metadata for saved product targeting and bounded discovery runs; use existing Lead/Company models, campaign membership, Celery and sending gate. No schema migration or new runtime dependency is needed.

- [NEW] backend/app/schemas/prospecting.py: validated product targeting, bounded runs and review selection.
- [NEW] backend/app/services/public_web.py: bounded public HTTP fetching, pinned public DNS destinations, robots rules, HTML/contact/location extraction.
- [NEW] backend/app/services/prospecting.py: Brave web search or supplied business websites, geographic evidence, relevance scoring, persistent progress/results.
- [NEW] backend/app/api/routes/prospecting.py: workspace-scoped profile, search status/history, review/import and campaign enrollment.
- [MODIFY] backend/app/main.py, core/config.py, worker/tasks.py: register endpoints and background task/provider configuration.
- [MODIFY] backend/app/api/routes/inbox.py: campaign/direction/channel/status filters and paginated message details.
- [NEW] backend/app/api/routes/email_analytics.py: campaign email cohort metrics, unique engagement counts and daily charts.
- [NEW] frontend/src/app/(app)/prospecting/page.tsx, frontend/src/components/email-analytics.tsx: targeting/review and campaign metrics.
- [MODIFY] frontend navigation/API/types, inbox/analytics/campaign pages: connect the full workflow.
- [NEW] focused backend tests: parsing/SSRF, targeting/radius, tenant isolation, import deduplication, message filters, metric correctness and simulated campaign integration.
- [MODIFY] README.md, .env.example: setup and coverage/measurement limits.

Verification: run isolated PostgreSQL tests, frontend TypeScript/production build, and inspect rendered pages if browser tooling is available. No real recipient mail is sent as part of verification.

Discovery covers publicly indexed and explicitly supplied websites, not the entire internet. Only observed contact emails are imported. Radius mode requires source-published coordinates; unknown positions are excluded. Product and target context support optional AI scoring through the existing provider; deterministic relevance evidence remains available without AI.
