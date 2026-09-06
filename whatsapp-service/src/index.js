// Internal WhatsApp messaging microservice (Phase 6).
//
// Mounts OpenWA (@open-wa/wa-automate) — UNOFFICIAL WhatsApp Web automation,
// ToS/ban risk on the connected number (accepted, documented). It stays
// white-labeled: no OpenWA branding is surfaced to end users.
//
// Runs in one of two modes:
//   • live  — @open-wa/wa-automate drives a real WhatsApp Web session (QR login).
//   • mock  — no browser/phone needed; fakes the QR→connected handshake and
//             send/receive so the whole stack is exercisable in dev + CI.
// Mode = mock when WHATSAPP_MOCK=1 or when @open-wa/wa-automate isn't installed
// (the default image omits it for fast, reliable builds — see Dockerfile).
//
// Every route except /health requires the internal shared-secret token. This
// service is never exposed publicly; only the backend/worker call it, and it
// calls the backend back on the same token for inbound messages.

import express from "express";

const app = express();
app.use(express.json({ limit: "1mb" }));

const PORT = process.env.PORT || 3100;
const TOKEN = process.env.WHATSAPP_SERVICE_TOKEN || "";
const BACKEND_URL = process.env.BACKEND_INTERNAL_URL || "http://backend:8000";
const SESSION_ID = process.env.WHATSAPP_SESSION_ID || "leadgen";
const FORCE_MOCK = process.env.WHATSAPP_MOCK === "1";

const log = (level, msg, extra = {}) =>
  console.log(JSON.stringify({ level, msg, ...extra }));

// ---- Session state (single WhatsApp number per service instance) ----
const session = {
  status: "disconnected", // disconnected | qr | connected | error
  qr: null, // data-URL of the pairing QR while status === "qr"
  me: null, // connected number, once paired
  mode: FORCE_MOCK ? "mock" : "unknown",
  error: null,
};

let waClient = null; // live @open-wa client, when in live mode

// ---- Inbound forwarding: push received messages to the backend webhook ----
async function forwardInbound({ from, body, id, timestamp }) {
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/whatsapp/webhook`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Service-Token": TOKEN },
      body: JSON.stringify({ from, body, provider_message_id: id, timestamp }),
    });
    if (!res.ok) log("warn", "webhook non-2xx", { status: res.status });
  } catch (err) {
    log("warn", "webhook forward failed", { err: String(err) });
  }
}

// ---- Mock mode: fake the QR handshake + echo path ----
function mockQrDataUrl() {
  // A self-contained SVG "QR" placeholder (no image libs needed).
  const svg =
    `<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>` +
    `<rect width='240' height='240' fill='#fff'/>` +
    `<rect x='20' y='20' width='200' height='200' fill='none' stroke='#111' stroke-width='6'/>` +
    `<text x='120' y='120' font-family='monospace' font-size='16' text-anchor='middle'>MOCK QR</text>` +
    `<text x='120' y='150' font-family='monospace' font-size='11' text-anchor='middle'>auto-connects…</text>` +
    `</svg>`;
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
}

function startMockSession() {
  session.mode = "mock";
  session.status = "qr";
  session.qr = mockQrDataUrl();
  session.error = null;
  // Simulate the user scanning the code shortly after.
  setTimeout(() => {
    session.status = "connected";
    session.qr = null;
    session.me = "15550000000";
    log("info", "mock session connected");
  }, 1500);
}

// ---- Live mode: drive @open-wa/wa-automate ----
async function startLiveSession() {
  let create;
  try {
    ({ create } = await import("@open-wa/wa-automate"));
  } catch (err) {
    log("warn", "@open-wa/wa-automate not installed — falling back to mock", { err: String(err) });
    startMockSession();
    return;
  }
  session.mode = "live";
  session.status = "qr";
  session.error = null;
  try {
    waClient = await create({
      sessionId: SESSION_ID,
      headless: true,
      qrTimeout: 0,
      authTimeout: 0,
      restartOnCrash: true,
      cacheEnabled: false,
      sessionDataPath: "/app/session",
      catchQR: (qrData) => {
        // qrData is a base64 PNG data-URL of the pairing code.
        session.status = "qr";
        session.qr = qrData;
      },
    });
    session.status = "connected";
    session.qr = null;
    try {
      const me = await waClient.getMe();
      session.me = me?.id?.user || me?.wid?.user || null;
    } catch {
      session.me = null;
    }
    waClient.onMessage(async (message) => {
      if (message.fromMe || message.isGroupMsg) return;
      await forwardInbound({
        from: message.from, // e.g. "15551234567@c.us"
        body: message.body || message.caption || "",
        id: message.id,
        timestamp: message.t,
      });
    });
    log("info", "live session connected");
  } catch (err) {
    session.status = "error";
    session.error = String(err);
    log("error", "live session failed", { err: String(err) });
  }
}

// ---- Send ----
function toChatId(to) {
  // Accept "+15551234567", "15551234567" or a full "…@c.us" and normalize.
  if (!to) return null;
  if (to.includes("@")) return to;
  const digits = String(to).replace(/\D+/g, "");
  return digits ? `${digits}@c.us` : null;
}

async function sendMessage(to, body) {
  const chatId = toChatId(to);
  if (!chatId) throw new Error("invalid recipient");
  if (session.status !== "connected") throw new Error("session not connected");

  if (session.mode === "mock") {
    return { id: `mock_${Date.now()}_${Math.random().toString(36).slice(2, 8)}` };
  }
  if (!waClient) throw new Error("no live client");
  const id = await waClient.sendText(chatId, body);
  return { id: typeof id === "string" ? id : id?._serialized || String(id) };
}

// ---- Auth guard ----
app.use((req, res, next) => {
  if (req.path === "/health") return next();
  if (!TOKEN || req.get("X-Service-Token") !== TOKEN) {
    return res.status(401).json({ error: "unauthorized" });
  }
  next();
});

app.get("/health", (_req, res) => {
  res.json({ status: "ok", provider: "openwa", mode: session.mode, connected: session.status === "connected" });
});

app.get("/session/status", (_req, res) => {
  res.json({ status: session.status, qr: session.qr, me: session.me, mode: session.mode, error: session.error });
});

app.post("/session/start", async (_req, res) => {
  if (session.status === "connected") {
    return res.json({ status: "connected", qr: null, me: session.me });
  }
  if (FORCE_MOCK) startMockSession();
  else startLiveSession(); // async; QR appears via /session/status polling
  res.json({ status: session.status, qr: session.qr, me: session.me });
});

app.post("/session/logout", async (_req, res) => {
  try {
    if (waClient) {
      try { await waClient.logout(); } catch {}
      try { await waClient.kill(); } catch {}
    }
  } finally {
    waClient = null;
    session.status = "disconnected";
    session.qr = null;
    session.me = null;
    session.error = null;
  }
  res.json({ status: "disconnected" });
});

app.post("/messages/send", async (req, res) => {
  // Outbound has ALREADY passed the backend can_send() gate before reaching here.
  const { to, body } = req.body || {};
  try {
    const result = await sendMessage(to, body);
    res.json({ success: true, id: result.id });
  } catch (err) {
    res.status(400).json({ success: false, error: String(err.message || err) });
  }
});

// Test hook (mock mode only): simulate an inbound reply from a number, so the
// full reply→webhook→sequence-halt path can be exercised end-to-end in dev/CI.
app.post("/mock/inbound", async (req, res) => {
  if (session.mode !== "mock") return res.status(400).json({ error: "not in mock mode" });
  const { from, body } = req.body || {};
  await forwardInbound({ from: toChatId(from), body: body || "", id: `mockin_${Date.now()}`, timestamp: Math.floor(Date.now() / 1000) });
  res.json({ ok: true });
});

app.listen(PORT, () => log("info", `whatsapp-service on :${PORT}`, { mode: session.mode }));
