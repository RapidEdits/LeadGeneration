import type {
  AIGeneration,
  AIResult,
  AIStatus,
  AnalyticsOutreach,
  AnalyticsOverview,
  AnalyticsTimeseries,
  CampaignPerformance,
  FunnelStage,
  AuthResponse,
  BulkQualifyResponse,
  Campaign,
  CampaignMember,
  CampaignMessage,
  CampaignStep,
  CanSendResult,
  Channel,
  ChannelConfig,
  Company,
  ConnectedAccount,
  DeliverabilityResponse,
  InboxItem,
  Lead,
  LeadFilter,
  LeadListResponse,
  LeadNote,
  LinkedInAccount,
  LinkedInTask,
  NLSearchResponse,
  PipelineResponse,
  Task,
  TaskStatus,
  TaskType,
  TimelineItem,
  WhatsAppSession,
  SuppressionEntry,
  Workspace,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const V1 = `${BASE}/api/v1`;

const TOKEN_KEY = "leadgen_token";
const WS_KEY = "leadgen_ws";
const PROFILE_KEY = "leadgen_profile";

export interface StoredProfile {
  user: { id: string; email: string; full_name: string | null };
  workspace: { id: string; name: string; slug: string; role: string };
}

export const session = {
  get token() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(TOKEN_KEY);
  },
  get workspaceId() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(WS_KEY);
  },
  get profile(): StoredProfile | null {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? (JSON.parse(raw) as StoredProfile) : null;
  },
  save(auth: AuthResponse) {
    localStorage.setItem(TOKEN_KEY, auth.access_token);
    localStorage.setItem(WS_KEY, auth.workspace.id);
    localStorage.setItem(
      PROFILE_KEY,
      JSON.stringify({ user: auth.user, workspace: auth.workspace }),
    );
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(WS_KEY);
    localStorage.removeItem(PROFILE_KEY);
  },
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (session.token) headers.set("Authorization", `Bearer ${session.token}`);
  if (session.workspaceId) headers.set("X-Workspace-Id", session.workspaceId);

  const res = await fetch(`${V1}${path}`, { ...init, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    session.clear();
    if (!window.location.pathname.startsWith("/sign-in")) {
      window.location.href = "/sign-in";
    }
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        // FastAPI/Pydantic validation errors: [{loc, msg, ...}]
        detail = body.detail
          .map((e: { loc?: (string | number)[]; msg?: string }) => {
            const field = e.loc?.filter((p) => p !== "body").join(".");
            return field ? `${field}: ${e.msg}` : e.msg;
          })
          .join("; ");
      }
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// Multipart (CSV upload) helper — no Content-Type header so the browser sets the boundary.
async function upload<T>(path: string, form: FormData): Promise<T> {
  const headers = new Headers();
  if (session.token) headers.set("Authorization", `Bearer ${session.token}`);
  if (session.workspaceId) headers.set("X-Workspace-Id", session.workspaceId);
  const res = await fetch(`${V1}${path}`, { method: "POST", body: form, headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.json() as Promise<T>;
}

export const api = {
  // Auth
  signup: (body: {
    email: string;
    password: string;
    full_name?: string;
    workspace_name: string;
  }) => request<AuthResponse>("/auth/signup", { method: "POST", body: JSON.stringify(body) }),
  login: (body: { email: string; password: string }) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  me: () => request<Lead>("/auth/me"),
  workspaces: () => request<Workspace[]>("/auth/workspaces"),

  // Leads
  searchLeads: (filter: LeadFilter) =>
    request<LeadListResponse>("/leads/search", { method: "POST", body: JSON.stringify(filter) }),
  getLead: (id: string) => request<Lead>(`/leads/${id}`),
  createLead: (body: Partial<Lead>) =>
    request<Lead>("/leads", { method: "POST", body: JSON.stringify(body) }),
  updateLead: (id: string, body: Partial<Lead>) =>
    request<Lead>(`/leads/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteLead: (id: string) => request<void>(`/leads/${id}`, { method: "DELETE" }),
  bulkLeads: (body: { lead_ids: string[]; action: string; status?: string; tag?: string }) =>
    request<{ affected: number }>("/leads/bulk", { method: "POST", body: JSON.stringify(body) }),
  duplicates: () =>
    request<{ key: string; match_type: string; lead_ids: string[] }[]>("/leads/duplicates/all"),

  // Companies
  listCompanies: (search?: string) =>
    request<Company[]>(`/companies${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  createCompany: (body: Partial<Company>) =>
    request<Company>("/companies", { method: "POST", body: JSON.stringify(body) }),

  // Campaigns
  listCampaigns: () => request<Campaign[]>("/campaigns"),
  getCampaign: (id: string) => request<Campaign>(`/campaigns/${id}`),
  createCampaign: (body: {
    name: string;
    description?: string;
    test_mode: boolean;
    approval_mode: "auto" | "manual";
    channels: Record<string, ChannelConfig>;
    steps: CampaignStep[];
  }) => request<Campaign>("/campaigns", { method: "POST", body: JSON.stringify(body) }),
  updateCampaign: (id: string, body: Partial<Campaign>) =>
    request<Campaign>(`/campaigns/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCampaign: (id: string) => request<void>(`/campaigns/${id}`, { method: "DELETE" }),
  addCampaignLeads: (id: string, lead_ids: string[]) =>
    request<{ added: number }>(`/campaigns/${id}/leads`, {
      method: "POST",
      body: JSON.stringify({ lead_ids }),
    }),
  campaignMembers: (id: string) => request<CampaignMember[]>(`/campaigns/${id}/leads`),
  campaignMessages: (id: string) => request<CampaignMessage[]>(`/campaigns/${id}/messages`),
  campaignTransition: (id: string, action: "launch" | "pause" | "resume" | "complete") =>
    request<{ id: string; state: string }>(`/campaigns/${id}/${action}`, { method: "POST" }),
  previewSend: (id: string, lead_id: string, channel: Channel) =>
    request<CanSendResult>(`/campaigns/${id}/preview-send`, {
      method: "POST",
      body: JSON.stringify({ lead_id, channel }),
    }),

  // Email accounts (Phase 3)
  listAccounts: () => request<ConnectedAccount[]>("/accounts"),
  connectSmtp: (body: {
    from_address: string;
    from_name?: string;
    host: string;
    port: number;
    username?: string;
    password?: string;
    use_tls?: boolean;
    use_ssl?: boolean;
    imap_host?: string;
    imap_port?: number;
    imap_username?: string;
    imap_password?: string;
    imap_ssl?: boolean;
  }) => request<ConnectedAccount>("/accounts/smtp", { method: "POST", body: JSON.stringify(body) }),
  disconnectAccount: (id: string) => request<void>(`/accounts/${id}`, { method: "DELETE" }),
  verifyAccount: (id: string) =>
    request<{ ok: boolean; detail: string | null }>(`/accounts/${id}/verify`, { method: "POST" }),
  testSend: (id: string, to_address: string) =>
    request<{ ok: boolean; detail: string | null }>(`/accounts/${id}/test`, {
      method: "POST",
      body: JSON.stringify({ to_address }),
    }),
  oauthStart: (provider: "google" | "microsoft") =>
    request<{ authorize_url: string }>(`/accounts/oauth/${provider}/start`),
  deliverabilityCheck: (body: { domain?: string; subject?: string; body?: string }) =>
    request<DeliverabilityResponse>("/accounts/deliverability/check", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // Inbox (Phase 3)
  inbox: () => request<InboxItem[]>("/inbox"),
  pollInbox: () =>
    request<{ outcomes: Record<string, number> }>("/inbox/poll", { method: "POST" }),

  // LinkedIn — assisted workflow (Phase 5)
  linkedinAccounts: () => request<LinkedInAccount[]>("/linkedin/account"),
  connectLinkedin: (body: { display_name: string; profile_url?: string | null }) =>
    request<LinkedInAccount>("/linkedin/account", { method: "POST", body: JSON.stringify(body) }),
  disconnectLinkedin: (id: string) =>
    request<void>(`/linkedin/account/${id}`, { method: "DELETE" }),
  linkedinTasks: () => request<LinkedInTask[]>("/linkedin/tasks"),
  completeLinkedinTask: (messageId: string, note?: string) =>
    request<{ ok: boolean; detail: string | null }>(`/linkedin/tasks/${messageId}/complete`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),
  skipLinkedinTask: (messageId: string, reason?: string) =>
    request<{ ok: boolean; detail: string | null }>(`/linkedin/tasks/${messageId}/skip`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),
  logLinkedinReply: (messageId: string, body: { text: string; from_name?: string | null }) =>
    request<{ ok: boolean; detail: string | null }>(`/linkedin/tasks/${messageId}/reply`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // WhatsApp — OpenWA microservice (Phase 6)
  whatsappSession: () => request<WhatsAppSession>("/whatsapp/session"),
  whatsappConnect: () => request<WhatsAppSession>("/whatsapp/connect", { method: "POST" }),
  whatsappDisconnect: () =>
    request<{ ok: boolean; detail: string | null }>("/whatsapp/disconnect", { method: "POST" }),

  // CRM — pipeline, tasks, notes, timeline (Phase 7)
  pipeline: () => request<PipelineResponse>("/crm/pipeline"),
  tasks: (scope = "open", params: { lead_id?: string; assignee_id?: string } = {}) => {
    const q = new URLSearchParams({ scope, ...(params.lead_id ? { lead_id: params.lead_id } : {}),
      ...(params.assignee_id ? { assignee_id: params.assignee_id } : {}) });
    return request<Task[]>(`/crm/tasks?${q.toString()}`);
  },
  createTask: (body: {
    title: string; type?: TaskType; description?: string | null;
    due_at?: string | null; lead_id?: string | null; assignee_id?: string | null;
  }) => request<Task>("/crm/tasks", { method: "POST", body: JSON.stringify(body) }),
  updateTask: (id: string, body: Partial<{ title: string; type: TaskType; status: TaskStatus;
    description: string | null; due_at: string | null; assignee_id: string | null }>) =>
    request<Task>(`/crm/tasks/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  completeTask: (id: string) => request<Task>(`/crm/tasks/${id}/complete`, { method: "POST" }),
  deleteTask: (id: string) => request<void>(`/crm/tasks/${id}`, { method: "DELETE" }),
  leadNotes: (leadId: string) => request<LeadNote[]>(`/crm/leads/${leadId}/notes`),
  createNote: (leadId: string, body: string) =>
    request<LeadNote>(`/crm/leads/${leadId}/notes`, { method: "POST", body: JSON.stringify({ body }) }),
  deleteNote: (id: string) => request<void>(`/crm/notes/${id}`, { method: "DELETE" }),
  leadTimeline: (leadId: string) => request<TimelineItem[]>(`/crm/leads/${leadId}/timeline`),

  // AI (Phase 4)
  aiStatus: () => request<AIStatus>("/ai/status"),
  aiQualify: (leadId: string, icp?: Record<string, unknown>) =>
    request<AIResult>(`/ai/qualify/${leadId}`, {
      method: "POST",
      body: JSON.stringify({ icp: icp ?? null }),
    }),
  aiQualifyBulk: (lead_ids: string[], icp?: Record<string, unknown>) =>
    request<BulkQualifyResponse>("/ai/qualify", {
      method: "POST",
      body: JSON.stringify({ lead_ids, icp: icp ?? null }),
    }),
  aiGenerateEmail: (lead_id: string, context?: Record<string, unknown>) =>
    request<AIResult>("/ai/generate/email", {
      method: "POST",
      body: JSON.stringify({ lead_id, context: context ?? null }),
    }),
  aiGenerateLinkedIn: (lead_id: string, context?: Record<string, unknown>) =>
    request<AIResult>("/ai/generate/linkedin", {
      method: "POST",
      body: JSON.stringify({ lead_id, context: context ?? null }),
    }),
  aiGenerateFollowUp: (lead_id: string, context?: Record<string, unknown>) =>
    request<AIResult>("/ai/generate/follow-up", {
      method: "POST",
      body: JSON.stringify({ lead_id, context: context ?? null }),
    }),
  aiClassifyReply: (body: { message?: string; message_id?: string }) =>
    request<AIResult>("/ai/classify-reply", { method: "POST", body: JSON.stringify(body) }),
  aiNlSearch: (query: string) =>
    request<NLSearchResponse>("/ai/nl-search", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  aiAnalyzeCampaign: (campaignId: string) =>
    request<AIResult>(`/ai/analyze-campaign/${campaignId}`, { method: "POST" }),
  aiCopilot: (question: string) =>
    request<AIResult>("/ai/copilot", { method: "POST", body: JSON.stringify({ question }) }),
  aiGenerations: (limit = 50) => request<AIGeneration[]>(`/ai/generations?limit=${limit}`),

  // Analytics (Phase 8)
  analyticsOverview: (days = 30) =>
    request<AnalyticsOverview>(`/analytics/overview?days=${days}`),
  analyticsFunnel: () => request<{ stages: FunnelStage[] }>("/analytics/funnel"),
  analyticsOutreach: (days = 30) =>
    request<AnalyticsOutreach>(`/analytics/outreach?days=${days}`),
  analyticsTimeseries: (days = 30) =>
    request<AnalyticsTimeseries>(`/analytics/timeseries?days=${days}`),
  analyticsCampaigns: () =>
    request<{ campaigns: CampaignPerformance[] }>("/analytics/campaigns"),
  analyticsInsights: (days = 30) =>
    request<{ result: AIResult }>(`/analytics/insights?days=${days}`, { method: "POST" }),

  // Suppression
  listSuppression: () => request<SuppressionEntry[]>("/suppression"),
  addSuppression: (body: { channel: string; value: string; reason?: string; note?: string }) =>
    request<SuppressionEntry>("/suppression", { method: "POST", body: JSON.stringify(body) }),

  // Imports
  previewCsv: (form: FormData) =>
    upload<{ headers: string[]; sample_rows: Record<string, string>[]; total_rows: number; importable_fields: string[] }>(
      "/imports/csv/preview",
      form,
    ),
  importCsv: (body: {
    column_map: Record<string, string>;
    rows: Record<string, unknown>[];
    source_name?: string;
  }) =>
    request<{
      created: number;
      duplicates_skipped: number;
      suppressed_skipped: number;
      errors: string[];
      source_id: string;
    }>("/imports/csv", { method: "POST", body: JSON.stringify(body) }),
};
