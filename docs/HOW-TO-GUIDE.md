# Lead Generator — How-To Guide

A plain-English walkthrough of what this product does and how to use it, start to
finish. No prior knowledge assumed. If you can use a spreadsheet and a web app,
you can use this.

---

## 1. What is this thing?

Lead Generator is a tool for **finding people to sell to, contacting them across
several channels, and tracking what happens** — all in one place, with safety
rules built in so you don't accidentally spam people or email someone who asked
you to stop.

The flow it supports, left to right:

```
  Import leads  →  Qualify (AI)  →  Put them in a Campaign  →  Reach out
   (CSV file)      (score fit)       (a sequence of steps)     (email / LinkedIn / WhatsApp)
                                                                     │
                                          Replies come back  ◄───────┘
                                                │
                                   Track in Pipeline + Tasks  →  See what's working (Analytics)
```

### The words you'll see

| Term | Plain meaning |
|---|---|
| **Workspace** | Your company's private space. All your data lives here; other workspaces can't see it. |
| **Lead** | One person you might sell to (name, email, job title, company…). |
| **Company** | The organization a lead works at. |
| **Campaign** | An outreach plan: which leads, which channels, and a **sequence** of messages with delays between them. |
| **Step** | One message in a campaign sequence (e.g. "Day 0: email", "Day 3: follow-up email"). |
| **Channel** | How you reach someone: **Email**, **LinkedIn**, or **WhatsApp**. |
| **Suppression list** | People you must never contact again (unsubscribed, bounced, complained). Checked automatically before every send. |
| **Pipeline** | A board (like Trello) showing which stage each lead is at: New → Qualified → Contacted → Replied → Won / Lost. |
| **Copilot** | An AI assistant you can ask questions about your workspace. |
| **`can_send` gate** | The single safety check every outbound message passes through. If any rule fails (suppressed, no consent, over the rate limit, wrong time of day…), the message is **not sent**. |

### Roles (who can do what)

- **Viewer** — read only.
- **Sales** — do the day-to-day work: leads, campaigns, tasks, sending.
- **Admin** — the above + delete campaigns, manage connected accounts.
- **Owner** — everything, including workspace settings.

---

## 2. First-time setup (one time only)

You need **Docker Desktop** installed and running. That's the only prerequisite —
it runs the database, the web app, the API, and the background worker for you.

```bash
# From the project folder:

# 1. Make your settings file
cp .env.example .env

# 2. Put real secret values in .env (open it in any text editor)
#    SECRET_KEY     — run: python -c "import secrets; print(secrets.token_urlsafe(48))"
#    ENCRYPTION_KEY — run: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 3. Start everything
docker compose up -d --build

# 4. Set up the database tables
docker compose run --rm backend alembic upgrade head
```

Now open **http://localhost:3000** in your browser.

> **Turning it off / on later:** `docker compose stop` to pause, `docker compose up -d`
> to resume. Your data is kept.

### Create your account

1. On the sign-up screen, enter your name, a **workspace name** (your company),
   your email, and a password.
2. Click **Create workspace**. You're now the **Owner** and land on the dashboard.

---

## 3. Turn on AI (recommended)

The AI features (lead scoring, writing emails, classifying replies, insights)
need one API key. Without it, those features simply say *"AI is unavailable"* —
nothing breaks, you just do that part manually.

**Default provider: DeepSeek** (a strong open model), via NVIDIA's free inference API.

1. Go to **https://build.nvidia.com**, sign in, open **Account → API Keys**, and
   create a key (free tier is fine to start).
2. Open your `.env` file and set:
   ```
   NVIDIA_API_KEY=nvapi-...your key...
   ```
   (`AI_PROVIDER=auto` and `DEEPSEEK_MODEL` are already set for you.)
3. Reload the services so they pick up the new key:
   ```bash
   docker compose up -d --force-recreate backend worker beat
   ```
   *(A plain `restart` is **not** enough — env changes need `up -d --force-recreate`.)*
4. Check it worked: **Settings → AI** should show **Enabled** with the model name.
   Or visit `http://localhost:8000/api/v1/ai/status`.

> **Switching models / providers:** change `DEEPSEEK_MODEL` (any model your key can
> access) or set `AI_PROVIDER=gemma` with a `GEMINI_API_KEY` to use Google's Gemma
> instead. Every AI feature routes through one internal interface, so nothing else
> changes.

> **Privacy note:** free AI tiers may log or train on what you send them. Fine for
> testing. For production with real customer data, use a paid no-retention
> endpoint (same `AI_BASE_URL` swap).

---

## 4. Get leads in

### Option A — Import a CSV (the normal way)

1. Go to **Leads → Import** (button top-right).
2. Drop in a `.csv` file. A wizard shows you the columns it found.
3. **Map your columns** to fields: `Full name → full_name`, `Work email → email`,
   `Job title → title`, `Company → company_name`, etc. Skip any you don't want.
4. Click import. You'll see a summary:
   - **Created** — new leads added.
   - **Duplicates skipped** — already in your workspace (matched on email, then
     LinkedIn URL, then phone, then name+company).
   - **Suppressed skipped** — on your do-not-contact list.

### Option B — Add one by hand

**Leads → Add lead**, fill the form, save.

### Clean-up: find duplicates

**Leads** has a duplicates view that groups likely-same people so you can merge
them.

---

## 5. Qualify leads with AI (optional but useful)

"Qualifying" = scoring how well a lead fits who you actually sell to, so you spend
time on the good ones.

1. On the **Leads** table, tick some leads (or tick the header box for all).
2. Click **Qualify with AI**.
3. Each lead gets a **score (0–100)** and a **verdict** (strong / medium / weak).
   Strong/medium leads that were still "New" get bumped to **Qualified**
   automatically.
4. Click a lead to see the AI's reasoning and the signals it used.

Every AI output is logged (**Settings → AI**, or the audit trail) so you can see
exactly what the model saw and said.

---

## 6. Connect a way to send

Before a campaign can send anything, connect at least one account under
**Settings**.

### Email

- **Gmail / Microsoft:** click **Connect**, sign in through the pop-up, approve.
  Tokens are stored encrypted; sending and reply-checking are automatic.
- **Any other provider (SMTP):** click **Add SMTP**, enter host / port / username /
  password. Optionally add **IMAP** details so replies and bounces are detected.
  Use **Test send** to confirm it works.
- **Deliverability check:** enter your domain to see SPF / DKIM / DMARC status and
  a spam-risk score for your message text.

### LinkedIn (assisted — no automation)

LinkedIn steps are **human-in-the-loop** on purpose (automating LinkedIn gets
accounts banned). Under **Settings → LinkedIn**, add your identity (your name +
profile URL). When a campaign reaches a LinkedIn step, it **drafts the message and
creates a task** — you send it yourself and mark it done. See §8.

### WhatsApp

**Settings → WhatsApp → Connect** shows a QR code. Scan it with WhatsApp on your
phone (Linked Devices). Once it says **Connected**, campaigns can send WhatsApp
messages automatically.

> ⚠️ WhatsApp uses an **unofficial** library (OpenWA). It breaks WhatsApp's terms
> and the number **can be banned**. Use a number you're willing to lose. In local
> testing it runs in a mock mode (no real phone needed).

---

## 7. Build and launch a campaign

1. **Campaigns → New campaign.**
2. **Name** it and pick **channels** (Email / LinkedIn / WhatsApp). Toggling a
   channel here is the real on/off switch — the backend enforces it.
3. Build the **sequence** — add steps in order, e.g.:
   | Step | Channel | Wait | Content |
   |---|---|---|---|
   | 1 | Email | 0 days | Subject + body. Use `{{first_name}}`, `{{company_name}}` for personalization. |
   | 2 | Email | 3 days | Follow-up. |
   | 3 | LinkedIn | 2 days | Connection note. |
   Optionally give a step an **AI personalization prompt** — the engine rewrites
   that step per-lead using the AI, and falls back to your template if the AI is
   unsure.
4. **Test mode** (default ON): the engine *simulates* sends so you can watch the
   sequence run without contacting anyone. Turn it off to send for real.
5. **Approval mode:** `auto` sends as scheduled; `manual` holds every outbound for
   a human OK.
6. Save, then open the campaign and **Add leads** (from your Leads list).
7. Click **Launch**.

### What happens after launch

A background worker wakes up every ~30 seconds and, for each lead that's due:

1. Runs the **`can_send` gate** — 8 checks: channel enabled? account connected?
   not suppressed? under the frequency cap? provider allowed? under the rate
   limit? within the send schedule? approval satisfied?
2. If all pass → sends (or simulates, in test mode), records the message, and
   schedules the next step.
3. If a lead **replies**, their sequence **stops** automatically.
4. A **hard bounce** auto-adds the address to the suppression list.
5. When every lead has finished or replied, the campaign **auto-completes**.

Watch progress on the campaign detail page (stats, sequence, per-lead status,
activity — it refreshes every few seconds).

---

## 8. Handle replies and manual tasks

### Inbox

**Inbox** shows every inbound reply across all campaigns. Connected mailboxes are
polled automatically; **Poll now** forces a check. If AI is on, each reply is
tagged with an **intent** (interested / not interested / question / meeting
request / unsubscribe / out-of-office…) and **sentiment**. An "unsubscribe" intent
auto-suppresses that person.

### LinkedIn Tasks

**LinkedIn Tasks** is your queue of drafted LinkedIn messages waiting for you to
send them:

- **Copy** the message, **Open profile**, send it on LinkedIn yourself.
- Click **Mark sent** — the campaign advances that lead to the next step.
- **Skip** if you don't want to send it.
- Got a reply on LinkedIn? Use **Log reply** so the system knows the lead
  responded (and halts their sequence).

### Tasks (general CRM)

**Tasks** is a to-do list for calls, emails, meetings, and reminders — attach them
to a lead, set a due date, tick them off. Scopes: Open / Overdue / Upcoming / Done.

---

## 9. Work the pipeline

**Pipeline** is a drag-and-drop board. Columns are lead **stages**:

```
New → Enriched → Qualified → Contacted → Replied → Won
                                              ↘ Lost / Disqualified
```

- **Drag a card** to move a lead to another stage (this just updates the lead —
  same as editing its status anywhere else).
- A card shows the lead's score, company, and a badge for open tasks.
- **Click a card** to open the lead's detail panel: contact info, stage,
  **add a note**, **add a task**, and a merged **Activity timeline** (every
  message, note, and task for that lead, newest first).

---

## 10. Read the analytics

**Analytics** answers "is this working?" Pick a time window (7 / 30 / 90 days) at
the top; everything updates.

- **KPI cards** — total & qualified leads, messages sent, reply rate, won count,
  win rate, open rate, overdue tasks.
- **Lead funnel** — how many leads reached each stage, and the conversion rate
  from the top.
- **Activity** — a daily line chart of sends, replies, and new leads.
- **Outreach by channel** — sent / opened / replied / bounced and the rates, per
  channel.
- **Campaign performance** — a table comparing every campaign.
- **AI insights** — click **Generate** and the AI reads your aggregate numbers and
  writes a short summary plus **strengths**, **issues**, and **recommendations**.
  If the AI is off or unsure, it says so rather than making things up.

---

## 11. Ask the Copilot

**AI Copilot** has two tabs:

- **Ask** — a chat box. "How many qualified leads do I have?" "Which campaign has
  the best reply rate?" It answers **only** from your real workspace data.
- **Lead search** — type a request in plain English ("CTOs in SaaS companies,
  sorted by score") and it builds the filter and runs the search.

---

## 12. Safety rules you can't turn off

These are enforced on the server, not just hidden in the UI:

- **Suppression is absolute.** Anyone unsubscribed / bounced / complained / manually
  blocked is never contacted, on any channel, by any campaign.
- **Frequency cap** across campaigns — a lead won't get hammered by two campaigns
  at once.
- **Send schedule** — messages only go out on the days/hours you configured.
- **One send path.** Every outbound — real or simulated, email or WhatsApp — goes
  through the same `can_send` gate. There is no "send anyway" button.
- **AI never decides to send.** It drafts and scores; the gate still governs
  whether anything goes out. And it returns "unknown" instead of inventing facts.
- **Full audit trail.** Every mutation, every AI generation (with the exact input
  it saw), every blocked send is logged.

---

## 13. Common problems

| Symptom | Fix |
|---|---|
| Can't reach http://localhost:3000 | `docker compose ps` — are all services "running"? `docker compose up -d` if not. |
| "AI is unavailable" everywhere | Key not set or not loaded. Check `.env` has `NVIDIA_API_KEY`, then `docker compose up -d --force-recreate backend worker beat`. |
| AI insights time out | The model is slow/overloaded on the free tier. Retry, or switch `DEEPSEEK_MODEL` to a lighter model, or `AI_PROVIDER=gemma`. |
| Campaign launched but nothing sends | It's probably in **Test mode** (simulated). Also check the channel is enabled, an account is connected, and the send schedule allows "now". |
| A new page in the UI 404s after an update | `docker compose restart frontend`. |
| Env change ignored | Env is injected at container **create** time. Use `docker compose up -d --force-recreate <service>`, not `restart`. |
| Replies not showing | For SMTP accounts you must add **IMAP** details. OAuth (Gmail/Microsoft) accounts poll automatically. |

---

## 14. Where things live (for the curious)

```
backend/app/
  api/routes/        one file per feature area (leads, campaigns, ai, analytics, crm…)
  services/
    can_send.py      the outbound safety gate
    engine.py        the campaign sequence runner (Celery worker)
    ai/              the AIService interface + DeepSeek / Gemma / Null implementations
  models/            database tables
frontend/src/
  app/(app)/         one folder per page
  lib/api.ts         every API call the UI makes
docs/HOW-TO-GUIDE.md this file
```

- **API reference:** http://localhost:8000/docs (interactive).
- **Run the tests:** `docker compose run --rm backend pytest`.
