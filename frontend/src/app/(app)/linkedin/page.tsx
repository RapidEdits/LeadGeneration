"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Linkedin, Loader2, RefreshCw, ExternalLink, Copy, Check, Send, X, CornerUpLeft,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { LinkedInTask } from "@/lib/types";

export default function LinkedInTasksPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["linkedin-tasks"],
    queryFn: () => api.linkedinTasks(),
    refetchInterval: 20000,
  });
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [copiedId, setCopiedId] = React.useState<string | null>(null);
  const [replyFor, setReplyFor] = React.useState<LinkedInTask | null>(null);

  const tasks = data ?? [];
  const refresh = () => qc.invalidateQueries({ queryKey: ["linkedin-tasks"] });

  const copy = async (t: LinkedInTask) => {
    try {
      await navigator.clipboard.writeText(t.body ?? "");
      setCopiedId(t.id);
      setTimeout(() => setCopiedId((c) => (c === t.id ? null : c)), 1500);
    } catch {
      toast.error("Couldn't copy to clipboard");
    }
  };

  const complete = async (t: LinkedInTask) => {
    setBusyId(t.id);
    try {
      await api.completeLinkedinTask(t.id);
      toast.success("Marked as sent — sequence advanced");
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not complete");
    } finally {
      setBusyId(null);
    }
  };

  const skip = async (t: LinkedInTask) => {
    const reason = prompt("Skip this message? Optional reason:") ?? undefined;
    setBusyId(t.id);
    try {
      await api.skipLinkedinTask(t.id, reason || undefined);
      toast.success("Task skipped");
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not skip");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="LinkedIn tasks"
        description="Assisted workflow — send each drafted message on LinkedIn, then mark it sent"
      >
        <Button variant="outline" onClick={refresh}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </PageHeader>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : tasks.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#0a66c2]/10 text-[#0a66c2]">
              <Linkedin className="h-6 w-6" />
            </div>
            <p className="max-w-md text-sm text-muted-foreground">
              No LinkedIn tasks waiting. When a live campaign reaches a LinkedIn step, the drafted
              message appears here for you to send manually and confirm. Connect a LinkedIn identity
              in Settings and take a campaign out of test mode to start.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {tasks.map((t) => (
            <Card key={t.id}>
              <CardContent className="space-y-3 py-4">
                <div className="flex flex-wrap items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold">{t.lead_name || "Unknown lead"}</span>
                      {t.lead_title && (
                        <span className="text-xs text-muted-foreground">{t.lead_title}</span>
                      )}
                      {t.campaign_name && (
                        <span className="rounded bg-accent px-1.5 py-0.5 text-xs text-accent-foreground">
                          {t.campaign_name}
                        </span>
                      )}
                    </div>
                    {t.profile_url && (
                      <a
                        href={t.profile_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-0.5 inline-flex items-center gap-1 text-xs text-[#0a66c2] hover:underline"
                      >
                        Open profile <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">{formatDate(t.created_at)}</span>
                </div>

                <div className="rounded-md border bg-muted/40 p-3 text-sm whitespace-pre-wrap">
                  {t.body || <span className="text-muted-foreground">(empty message)</span>}
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={() => copy(t)}>
                    {copiedId === t.id ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    {copiedId === t.id ? "Copied" : "Copy message"}
                  </Button>
                  <Button size="sm" onClick={() => complete(t)} disabled={busyId === t.id}>
                    {busyId === t.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                    Mark as sent
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setReplyFor(t)}>
                    <CornerUpLeft className="h-3.5 w-3.5" /> Log reply
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => skip(t)} disabled={busyId === t.id}>
                    <X className="h-3.5 w-3.5" /> Skip
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <LogReplyDialog
        task={replyFor}
        onClose={() => setReplyFor(null)}
        onLogged={() => {
          setReplyFor(null);
          refresh();
        }}
      />
    </div>
  );
}

function LogReplyDialog({
  task,
  onClose,
  onLogged,
}: {
  task: LinkedInTask | null;
  onClose: () => void;
  onLogged: () => void;
}) {
  const [text, setText] = React.useState("");
  const [fromName, setFromName] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (task) {
      setText("");
      setFromName(task.lead_name ?? "");
    }
  }, [task]);

  const submit = async () => {
    if (!task) return;
    if (!text.trim()) return toast.error("Enter the reply text");
    setBusy(true);
    try {
      await api.logLinkedinReply(task.id, { text: text.trim(), from_name: fromName.trim() || null });
      toast.success("Reply logged — sequence halted for this lead");
      onLogged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not log reply");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={task !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Log a LinkedIn reply</DialogTitle>
          <DialogDescription>
            Paste what {task?.lead_name || "the lead"} replied on LinkedIn. This records it in the
            inbox, halts their sequence, and runs AI classification.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="From (name)"
            value={fromName}
            onChange={(e) => setFromName(e.target.value)}
          />
          <textarea
            placeholder="Their reply…"
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CornerUpLeft className="h-4 w-4" />}
            Log reply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
