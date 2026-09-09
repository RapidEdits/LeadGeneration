"use client";
import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Play, Pause, CheckCircle2, RotateCcw, UserPlus, Users, Send,
  FlaskConical, Mail, Linkedin, MessageCircle, Clock, Sparkles, Loader2, Pencil,
} from "lucide-react";
import type { AIResult } from "@/lib/types";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { CampaignStateBadge } from "@/components/campaign-state-badge";
import { CampaignBuilder } from "@/components/campaign-builder";
import { AddLeadsToCampaign } from "@/components/add-leads-to-campaign";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { CampaignLeadState, Channel } from "@/lib/types";

const CHANNEL_ICON: Record<Channel, React.ElementType> = {
  email: Mail, linkedin: Linkedin, whatsapp: MessageCircle,
};

const MEMBER_VARIANT: Record<CampaignLeadState, "default" | "secondary" | "success" | "warning" | "destructive" | "outline"> = {
  pending: "secondary", active: "default", replied: "success", completed: "success",
  bounced: "destructive", failed: "destructive", skipped: "outline", awaiting_action: "warning",
};

// Raw engine block/skip codes → plain English shown in the Note column.
const REASON_LABEL: Record<string, string> = {
  frequency_ok: "Waiting — this lead was contacted too recently",
  account_connected: "Waiting for a connected sending account",
  rate_limit_ok: "Daily send limit reached — resumes later",
  schedule_ok: "Outside the campaign's sending window",
  approval_satisfied: "Waiting for approval before sending",
  not_suppressed: "Skipped — address is suppressed (unsubscribed or bounced)",
  suppressed: "Skipped — address is suppressed (unsubscribed or bounced)",
  send_failed: "Last send failed — retrying",
  awaiting_action: "Waiting for a manual send (LinkedIn)",
  bounced: "Bounced — stopped contacting this lead",
  blocked: "Blocked by a send rule",
  replied: "Lead replied — sequence stopped",
};

/** Human-readable explanation of where a member stands. */
function memberNote(m: { state: CampaignLeadState; last_reason: string | null }): string {
  if (m.last_reason) return REASON_LABEL[m.last_reason] ?? m.last_reason;
  if (m.state === "pending") return "Not scheduled yet — launch or resume the campaign to start";
  return "—";
}

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();

  const campaign = useQuery({ queryKey: ["campaign", id], queryFn: () => api.getCampaign(id), refetchInterval: 5000 });
  const members = useQuery({ queryKey: ["campaign-members", id], queryFn: () => api.campaignMembers(id) });
  const messages = useQuery({ queryKey: ["campaign-messages", id], queryFn: () => api.campaignMessages(id), refetchInterval: 5000 });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["campaign", id] });
    qc.invalidateQueries({ queryKey: ["campaign-members", id] });
    qc.invalidateQueries({ queryKey: ["campaign-messages", id] });
  };

  const [analysis, setAnalysis] = React.useState<AIResult | null>(null);
  const [analyzing, setAnalyzing] = React.useState(false);

  const analyze = async () => {
    setAnalyzing(true);
    try {
      const res = await api.aiAnalyzeCampaign(id);
      setAnalysis(res);
      if (res.status !== "ok") toast.message("AI is disabled or unsure — set GEMINI_API_KEY to enable.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  };

  const transition = async (action: "launch" | "pause" | "resume" | "complete") => {
    try {
      await api.campaignTransition(id, action);
      toast.success(`Campaign ${action === "launch" ? "launched" : action + "d"}`);
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : `Could not ${action}`);
    }
  };

  // --- Edit orchestration ---
  // An active campaign must be paused before it can be edited (backend rule),
  // then resumed after saving so it goes back to running on its own.
  const [editOpen, setEditOpen] = React.useState(false);
  const [confirmPause, setConfirmPause] = React.useState(false);
  const autoPaused = React.useRef(false);
  const justSaved = React.useRef(false);

  const openEditor = () => { autoPaused.current = false; setEditOpen(true); };

  const startEdit = () => {
    if (campaign.data?.state === "active") setConfirmPause(true);
    else openEditor();
  };

  const confirmPauseAndEdit = async () => {
    try {
      await api.campaignTransition(id, "pause");
      autoPaused.current = true;
      setConfirmPause(false);
      qc.invalidateQueries({ queryKey: ["campaign", id] });
      setEditOpen(true);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not pause campaign");
    }
  };

  const resumeIfAutoPaused = async (savedMsg?: string) => {
    if (!autoPaused.current) return;
    autoPaused.current = false;
    try {
      await api.campaignTransition(id, "resume");
      if (savedMsg) toast.success(savedMsg);
    } catch {
      toast.error(
        savedMsg
          ? "Saved, but the campaign stayed paused — resume it manually."
          : "Could not resume — the campaign stayed paused.",
      );
    } finally {
      refresh();
    }
  };

  const handleEditSaved = () => {
    justSaved.current = true;
    resumeIfAutoPaused("Campaign resumed");
    refresh();
  };

  const handleEditOpenChange = (v: boolean) => {
    setEditOpen(v);
    if (!v) {
      // Closed. If it was a save, handleEditSaved already dealt with resume.
      if (justSaved.current) { justSaved.current = false; return; }
      // Cancelled after we auto-paused → put it back to running.
      resumeIfAutoPaused();
    }
  };

  const c = campaign.data;

  if (campaign.isLoading || !c) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      </div>
    );
  }

  const st = c.stats;
  const canLaunch = c.state === "draft" || c.state === "scheduled";
  const canPause = c.state === "active";
  const canResume = c.state === "paused";
  const canComplete = c.state === "active" || c.state === "paused";
  // Backend permits edits in draft/scheduled/paused; active is allowed via pause-then-resume.
  const canEdit = ["draft", "scheduled", "paused", "active"].includes(c.state);

  return (
    <div>
      <button onClick={() => router.push("/campaigns")} className="mb-4 flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Campaigns
      </button>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{c.name}</h1>
            <CampaignStateBadge state={c.state} />
            {c.test_mode && <Badge variant="outline" className="gap-1"><FlaskConical className="h-3 w-3" /> Test mode</Badge>}
          </div>
          {c.description && <p className="text-sm text-muted-foreground">{c.description}</p>}
        </div>
        <div className="flex items-center gap-2">
          {canEdit && (
            <Button variant="outline" onClick={startEdit}>
              <Pencil className="h-4 w-4" /> Edit
            </Button>
          )}
          <Button variant="outline" onClick={analyze} disabled={analyzing}>
            {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Analyze with AI
          </Button>
          {canLaunch && <Button onClick={() => transition("launch")}><Play className="h-4 w-4" /> Launch</Button>}
          {canPause && <Button variant="outline" onClick={() => transition("pause")}><Pause className="h-4 w-4" /> Pause</Button>}
          {canResume && <Button onClick={() => transition("resume")}><Play className="h-4 w-4" /> Resume</Button>}
          {canComplete && <Button variant="outline" onClick={() => transition("complete")}><CheckCircle2 className="h-4 w-4" /> Complete</Button>}
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={Users} label="Leads" value={st?.total ?? 0} />
        <Stat icon={Send} label="Messages sent" value={st?.messages_sent ?? 0} />
        <Stat icon={RotateCcw} label="In progress" value={st?.active ?? 0} />
        <Stat icon={CheckCircle2} label="Completed" value={st?.completed ?? 0} />
      </div>

      {analysis && analysis.status === "ok" && (
        <Card className="mt-4 border-primary/30 bg-primary/5">
          <CardContent className="p-4">
            <div className="mb-2 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              <span className="font-medium">AI campaign analysis</span>
              {analysis.model && <Badge variant="outline" className="text-[10px]">{analysis.model}</Badge>}
            </div>
            {typeof analysis.output.summary === "string" && (
              <p className="text-sm text-muted-foreground">{analysis.output.summary}</p>
            )}
            <div className="mt-3 grid gap-4 sm:grid-cols-3">
              {(["strengths", "issues", "recommendations"] as const).map((key) => {
                const list = analysis.output[key];
                if (!Array.isArray(list) || list.length === 0) return null;
                return (
                  <div key={key}>
                    <div className="mb-1 text-xs font-medium capitalize text-muted-foreground">{key}</div>
                    <ul className="list-inside list-disc space-y-1 text-sm">
                      {list.map((item, i) => <li key={i}>{String(item)}</li>)}
                    </ul>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="sequence" className="mt-6">
        <TabsList>
          <TabsTrigger value="sequence">Sequence</TabsTrigger>
          <TabsTrigger value="leads">Leads {st ? `(${st.total})` : ""}</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>

        {/* Sequence */}
        <TabsContent value="sequence">
          <div className="space-y-3">
            {c.steps.map((s, i) => {
              const Icon = CHANNEL_ICON[s.channel];
              return (
                <Card key={s.id ?? i}>
                  <CardContent className="flex gap-4 p-4">
                    <div className="flex flex-col items-center">
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-accent-foreground">
                        <Icon className="h-4 w-4" />
                      </div>
                      {i < c.steps.length - 1 && <div className="mt-1 h-full w-px flex-1 bg-border" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">Step {i + 1}</span>
                        <Badge variant="secondary" className="capitalize">{s.channel}</Badge>
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Clock className="h-3 w-3" /> wait {s.delay_days}d
                        </span>
                      </div>
                      {s.subject && <div className="mt-1 text-sm font-medium">{s.subject}</div>}
                      {s.body_template && <div className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">{s.body_template}</div>}
                      {s.ai_prompt && (
                        <div className="mt-2 flex items-start gap-1.5 rounded-md bg-primary/5 px-2 py-1.5 text-xs text-muted-foreground">
                          <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-primary" />
                          <span>AI personalization: {s.ai_prompt}</span>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {Object.entries(c.channels).map(([ch, cfg]) => (
              <Badge key={ch} variant={cfg.enabled ? "success" : "outline"} className="capitalize">
                {ch}: {cfg.enabled ? `on${cfg.daily_limit ? ` · ${cfg.daily_limit}/day` : ""}` : "off"}
              </Badge>
            ))}
          </div>
        </TabsContent>

        {/* Leads */}
        <TabsContent value="leads">
          <div className="mb-3 flex justify-end">
            <AddLeadsToCampaign
              campaignId={id}
              onAdded={refresh}
              trigger={<Button size="sm"><UserPlus className="h-4 w-4" /> Add leads</Button>}
            />
          </div>
          <div className="rounded-xl border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Lead</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Step</TableHead>
                  <TableHead>Next action</TableHead>
                  <TableHead>Note</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(members.data ?? []).length === 0 && (
                  <TableRow><TableCell colSpan={6}>
                    <p className="py-8 text-center text-sm text-muted-foreground">
                      No leads yet. Add leads, then launch to start the sequence.
                    </p>
                  </TableCell></TableRow>
                )}
                {(members.data ?? []).map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="font-medium">{m.lead_name || "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{m.lead_email || "—"}</TableCell>
                    <TableCell><Badge variant={MEMBER_VARIANT[m.state]} className="capitalize">{m.state}</Badge></TableCell>
                    <TableCell>{m.current_step + 1}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {m.next_action_at ? new Date(m.next_action_at).toLocaleString() : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground" title={m.last_reason ?? undefined}>
                      {memberNote(m)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        {/* Activity */}
        <TabsContent value="activity">
          <div className="rounded-xl border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Channel</TableHead>
                  <TableHead>To</TableHead>
                  <TableHead>Subject</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(messages.data ?? []).length === 0 && (
                  <TableRow><TableCell colSpan={5}>
                    <p className="py-8 text-center text-sm text-muted-foreground">
                      No messages yet. Launch the campaign to begin sending.
                    </p>
                  </TableCell></TableRow>
                )}
                {(messages.data ?? []).map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="text-muted-foreground">{new Date(m.created_at).toLocaleString()}</TableCell>
                    <TableCell className="capitalize">{m.channel}</TableCell>
                    <TableCell className="text-muted-foreground">{m.to_address || "—"}</TableCell>
                    <TableCell>{m.subject || "—"}</TableCell>
                    <TableCell>
                      <Badge variant={m.status === "simulated" ? "secondary" : m.status === "failed" ? "destructive" : "success"}>
                        {m.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {c.test_mode && (messages.data ?? []).length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              <FlaskConical className="mr-1 inline h-3 w-3" />
              Test mode — these sends are simulated. No real messages left your accounts.
            </p>
          )}
        </TabsContent>
      </Tabs>

      {/* Edit dialog (reuses the campaign builder in edit mode) */}
      <CampaignBuilder
        campaign={c}
        open={editOpen}
        onOpenChange={handleEditOpenChange}
        onSaved={handleEditSaved}
        trigger={<span className="hidden" />}
      />

      {/* Confirm pause-to-edit for a running campaign */}
      <Dialog open={confirmPause} onOpenChange={setConfirmPause}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Pause to edit?</DialogTitle>
            <DialogDescription>
              This campaign is running. It&apos;ll be paused while you edit and resume
              automatically once you save your changes.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmPause(false)}>Cancel</Button>
            <Button onClick={confirmPauseAndEdit}><Pause className="h-4 w-4" /> Pause &amp; edit</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Stat({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="text-xl font-semibold">{value}</div>
        </div>
      </CardContent>
    </Card>
  );
}
