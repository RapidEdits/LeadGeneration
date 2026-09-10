export type Role = "owner" | "admin" | "sales" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  role: Role;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
  workspace: Workspace;
}

export type LeadStatus =
  | "new" | "enriched" | "qualified" | "contacted"
  | "replied" | "won" | "lost" | "disqualified";

export type CampaignStatus = "none" | "queued" | "active" | "paused" | "completed";

export interface Lead {
  id: string;
  workspace_id: string;
  full_name: string | null;
  first_name: string | null;
  last_name: string | null;
  title: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  location: string | null;
  company_id: string | null;
  status: LeadStatus;
  campaign_status: CampaignStatus;
  score: number | null;
  email_provenance: "observed" | "estimated" | "unknown";
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadListResponse {
  items: Lead[];
  total: number;
  page: number;
  page_size: number;
}

export interface Company {
  id: string;
  workspace_id: string;
  name: string;
  domain: string | null;
  website: string | null;
  industry: string | null;
  size: string | null;
  location: string | null;
  linkedin_url: string | null;
  description: string | null;
  lead_count: number;
  created_at: string;
  updated_at: string;
}

export interface SuppressionEntry {
  id: string;
  channel: string;
  value: string;
  reason: string;
  note: string | null;
  created_at: string;
}

export type Channel = "email" | "linkedin" | "whatsapp";
export type CampaignState = "draft" | "scheduled" | "active" | "paused" | "completed" | "archived";
export type CampaignLeadState =
  | "pending" | "active" | "replied" | "bounced" | "failed" | "skipped" | "awaiting_action" | "completed";

export interface ChannelConfig {
  enabled: boolean;
  daily_limit?: number | null;
  schedule?: { days?: number[] | null; start?: string | null; end?: string | null; tz?: string } | null;
}

export interface CampaignStep {
  id?: string;
  order_index?: number;
  channel: Channel;
  delay_days: number;
  subject?: string | null;
  body_template?: string | null;
  ai_prompt?: string | null;
  enabled: boolean;
}

export interface CampaignStats {
  total: number;
  pending: number;
  active: number;
  completed: number;
  replied: number;
  skipped: number;
  failed: number;
  awaiting_action: number;
  messages_sent: number;
}

export interface Campaign {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  state: CampaignState;
  test_mode: boolean;
  approval_mode: "auto" | "manual";
  channels: Record<string, ChannelConfig>;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  steps: CampaignStep[];
  stats?: CampaignStats | null;
}

export interface CampaignMember {
  id: string;
  lead_id: string;
  state: CampaignLeadState;
  current_step: number;
  next_action_at: string | null;
  last_sent_at: string | null;
  attempts: number;
  last_reason: string | null;
  lead_name: string | null;
  lead_email: string | null;
}

export interface CampaignMessage {
  id: string;
  channel: Channel;
  direction: string;
  status: string;
  subject: string | null;
  body: string | null;
  to_address: string | null;
  lead_id: string | null;
  created_at: string;
}

export interface CanSendResult {
  allowed: boolean;
  reasons: string[];
  checks: Record<string, boolean>;
}

export interface ConnectedAccount {
  id: string;
  provider: "gmail" | "microsoft" | "smtp";
  type: string;
  display_name: string | null;
  external_id: string | null;
  status: "connected" | "disconnected" | "error";
  from_address: string | null;
  from_name: string | null;
  can_receive: boolean;
  created_at: string;
}

export interface DomainDeliverability {
  domain: string;
  error?: string;
  checks?: { mx: boolean; spf: boolean; dmarc: boolean; dkim: boolean };
  records?: { spf: string | null; dmarc: string | null; dkim_selectors: string[] };
  dmarc_policy?: string | null;
  auth_score?: number;
  recommendations?: string[];
}

export interface ContentDeliverability {
  score: number;
  issues: string[];
  word_count: number;
  link_count: number;
}

export interface DeliverabilityResponse {
  domain: DomainDeliverability | null;
  content: ContentDeliverability | null;
}

export interface InboxItem {
  id: string;
  channel: Channel;
  subject: string | null;
  body: string | null;
  from_address: string | null;
  lead_id: string | null;
  lead_name: string | null;
  campaign_id: string | null;
  campaign_name: string | null;
  direction: "inbound" | "outbound";
  status: string;
  to_address: string | null;
  events: { type: string; created_at: string; provenance: string; error: string | null }[];
  created_at: string;
}

export interface ProductProfile {
  name: string; overview: string; website: string; target_customer: string;
  locations: string[]; country_code: string; max_leads: number;
  radius_km: number | null; latitude: number | null; longitude: number | null;
}
export interface ProspectCandidate {
  id: string; company: string; website: string; email: string; source_url: string;
  location: string; location_evidence: string; location_source: string;
  distance_km: number | null; score: number; reason: string;
  ai_score: number | null; ai_reason: string | null; lead_id: string | null; observed_at: string;
}
export interface DiscoveryRun {
  id: string; created_at: string; status: "queued" | "running" | "completed" | "failed";
  profile: ProductProfile; candidates: ProspectCandidate[]; warnings: string[];
  sites_total: number; sites_scanned: number; filtered: number; queries: string[]; error: string | null;
}
export interface EmailMetrics {
  campaign_id: string | null; days: number; definition: string;
  totals: Record<string, number>; rates: Record<string, number>;
  points: ({ date: string } & Record<string, number | string>)[];
}

// ---- LinkedIn assisted workflow (Phase 5) ----
export interface LinkedInAccount {
  id: string;
  provider: string;
  display_name: string | null;
  profile_url: string | null;
  status: string;
  created_at: string;
}

export interface LinkedInTask {
  id: string;
  lead_id: string | null;
  lead_name: string | null;
  lead_title: string | null;
  profile_url: string | null;
  campaign_id: string | null;
  campaign_name: string | null;
  body: string | null;
  created_at: string;
}

// ---- CRM (Phase 7) ----
export type TaskType = "todo" | "call" | "email" | "meeting" | "linkedin";
export type TaskStatus = "open" | "done" | "cancelled";

export interface Task {
  id: string;
  type: TaskType;
  status: TaskStatus;
  title: string;
  description: string | null;
  due_at: string | null;
  completed_at: string | null;
  lead_id: string | null;
  lead_name: string | null;
  assignee_id: string | null;
  assignee_name: string | null;
  created_at: string;
}

export interface LeadNote {
  id: string;
  lead_id: string;
  body: string;
  author_id: string | null;
  author_name: string | null;
  created_at: string;
}

export interface TimelineItem {
  kind: "message" | "note" | "task" | "event";
  id: string;
  at: string;
  title: string | null;
  body: string | null;
  channel: string | null;
  direction: string | null;
  status: string | null;
  actor: string | null;
  meta: Record<string, unknown> | null;
}

export interface PipelineCard {
  id: string;
  full_name: string | null;
  title: string | null;
  company_name: string | null;
  email: string | null;
  score: number | null;
  status: LeadStatus;
  updated_at: string;
  open_tasks: number;
}

export interface PipelineStage {
  status: LeadStatus;
  label: string;
  count: number;
  cards: PipelineCard[];
}

export interface PipelineResponse {
  stages: PipelineStage[];
}

// ---- WhatsApp (Phase 6) ----
export interface WhatsAppSession {
  status: "disconnected" | "qr" | "connected" | "error";
  qr: string | null;
  me: string | null;
  mode: string | null;
  error: string | null;
  account_id: string | null;
  connected_at: string | null;
}

export interface FilterCondition {
  field: string;
  op: string;
  value?: unknown;
}

// ---- AI (Phase 4) ----
export interface AIStatus {
  enabled: boolean;
  model: string | null;
}

export interface AIResult {
  status: "ok" | "unknown" | "error";
  kind: string | null;
  model: string | null;
  output: Record<string, unknown>;
  assumptions: string[];
  latency_ms: number | null;
  error: string | null;
}

export interface BulkQualifyItem {
  lead_id: string;
  status: string;
  score: number | null;
  verdict: string | null;
}

export interface BulkQualifyResponse {
  processed: number;
  results: BulkQualifyItem[];
}

export interface NLSearchResponse {
  result: AIResult;
  filter: LeadFilter;
  leads: LeadListResponse;
}

export interface AIGeneration {
  id: string;
  kind: string;
  model: string | null;
  status: string;
  lead_id: string | null;
  campaign_id: string | null;
  output: Record<string, unknown> | null;
  assumptions: unknown[] | null;
  latency_ms: number | null;
  created_at: string;
}

// ---- Analytics (Phase 8) ----
export interface AnalyticsOverview {
  days: number;
  total_leads: number;
  new_leads: number;
  qualified_leads: number;
  contacted_leads: number;
  replied_leads: number;
  won_leads: number;
  lost_leads: number;
  active_campaigns: number;
  messages_sent: number;
  replies_received: number;
  reply_rate: number;
  win_rate: number;
  open_tasks: number;
  overdue_tasks: number;
}

export interface FunnelStage {
  status: string;
  label: string;
  count: number;
  conversion_from_top: number;
}

export interface ChannelBreakdown {
  channel: string;
  sent: number;
  opened: number;
  clicked: number;
  replied: number;
  bounced: number;
  open_rate: number;
  reply_rate: number;
  bounce_rate: number;
}

export interface AnalyticsOutreach {
  days: number;
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  total_replied: number;
  total_bounced: number;
  open_rate: number;
  click_rate: number;
  reply_rate: number;
  bounce_rate: number;
  by_channel: ChannelBreakdown[];
}

export interface TimeseriesPoint {
  date: string;
  leads_created: number;
  messages_sent: number;
  replies: number;
}

export interface AnalyticsTimeseries {
  days: number;
  points: TimeseriesPoint[];
}

export interface CampaignPerformance {
  id: string;
  name: string;
  state: string;
  total_leads: number;
  messages_sent: number;
  opened: number;
  replied: number;
  bounced: number;
  reply_rate: number;
  open_rate: number;
  bounce_rate: number;
}

export interface LeadFilter {
  match?: "all" | "any";
  conditions?: FilterCondition[];
  search?: string;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
}
