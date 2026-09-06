"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  X, Mail, MessageCircle, Linkedin, StickyNote, CheckSquare, Send, CornerUpLeft,
  Loader2, Plus, Calendar, Phone,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api, ApiError } from "@/lib/api";
import { formatDate, initials } from "@/lib/utils";
import type { LeadStatus, TaskType, TimelineItem } from "@/lib/types";

const STAGES: { value: LeadStatus; label: string }[] = [
  { value: "new", label: "New" },
  { value: "enriched", label: "Enriched" },
  { value: "qualified", label: "Qualified" },
  { value: "contacted", label: "Contacted" },
  { value: "replied", label: "Replied" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
  { value: "disqualified", label: "Disqualified" },
];

const CHANNEL_ICON: Record<string, React.ElementType> = {
  email: Mail, whatsapp: MessageCircle, linkedin: Linkedin,
};

export function LeadDetailDrawer({
  leadId,
  onClose,
  onChanged,
}: {
  leadId: string | null;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const qc = useQueryClient();
  const open = leadId !== null;

  const { data: lead } = useQuery({
    queryKey: ["lead", leadId],
    queryFn: () => api.getLead(leadId!),
    enabled: open,
  });
  const { data: timeline, isLoading } = useQuery({
    queryKey: ["lead-timeline", leadId],
    queryFn: () => api.leadTimeline(leadId!),
    enabled: open,
  });

  const [note, setNote] = React.useState("");
  const [taskTitle, setTaskTitle] = React.useState("");
  const [taskType, setTaskType] = React.useState<TaskType>("todo");
  const [busy, setBusy] = React.useState(false);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["lead-timeline", leadId] });
    qc.invalidateQueries({ queryKey: ["pipeline"] });
    qc.invalidateQueries({ queryKey: ["tasks"] });
    onChanged?.();
  };

  const addNote = async () => {
    if (!note.trim() || !leadId) return;
    setBusy(true);
    try {
      await api.createNote(leadId, note.trim());
      setNote("");
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not add note");
    } finally {
      setBusy(false);
    }
  };

  const addTask = async () => {
    if (!taskTitle.trim() || !leadId) return;
    setBusy(true);
    try {
      await api.createTask({ title: taskTitle.trim(), type: taskType, lead_id: leadId });
      setTaskTitle("");
      toast.success("Task added");
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not add task");
    } finally {
      setBusy(false);
    }
  };

  const changeStage = async (status: LeadStatus) => {
    if (!leadId) return;
    try {
      await api.updateLead(leadId, { status });
      qc.invalidateQueries({ queryKey: ["lead", leadId] });
      refresh();
    } catch {
      toast.error("Could not update stage");
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-md flex-col border-l bg-background shadow-xl">
        <header className="flex items-start justify-between border-b p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-accent text-sm font-medium">
              {initials(lead?.full_name)}
            </div>
            <div>
              <div className="font-semibold">{lead?.full_name || "Lead"}</div>
              <div className="text-xs text-muted-foreground">
                {lead?.title}
                {lead?.title && lead?.email ? " · " : ""}
                {lead?.email}
              </div>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto p-4">
          {/* Contact chips */}
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {lead?.phone && <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{lead.phone}</span>}
            {lead?.linkedin_url && (
              <a href={lead.linkedin_url} target="_blank" rel="noreferrer"
                className="flex items-center gap-1 text-[#0a66c2] hover:underline">
                <Linkedin className="h-3 w-3" /> Profile
              </a>
            )}
            {typeof lead?.score === "number" && (
              <span className="flex items-center gap-1">Score {Math.round(lead.score)}</span>
            )}
          </div>

          {/* Stage selector */}
          <div>
            <div className="mb-1.5 text-xs font-medium text-muted-foreground">Pipeline stage</div>
            <div className="flex flex-wrap gap-1.5">
              {STAGES.map((s) => (
                <button
                  key={s.value}
                  onClick={() => changeStage(s.value)}
                  className={
                    "rounded-full px-2.5 py-1 text-xs transition-colors " +
                    (lead?.status === s.value
                      ? "bg-primary text-primary-foreground"
                      : "bg-accent text-accent-foreground hover:bg-accent/70")
                  }
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Add note + task */}
          <div className="space-y-2 rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <StickyNote className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Add a note</span>
            </div>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="Log a call, a detail, next steps…"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
            <div className="flex justify-end">
              <Button size="sm" onClick={addNote} disabled={busy || !note.trim()}>
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Save note
              </Button>
            </div>
          </div>

          <div className="space-y-2 rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <CheckSquare className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Add a task</span>
            </div>
            <div className="flex gap-2">
              <select
                value={taskType}
                onChange={(e) => setTaskType(e.target.value as TaskType)}
                className="rounded-md border border-input bg-background px-2 text-sm"
              >
                <option value="todo">To-do</option>
                <option value="call">Call</option>
                <option value="email">Email</option>
                <option value="meeting">Meeting</option>
                <option value="linkedin">LinkedIn</option>
              </select>
              <Input value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)}
                placeholder="What needs doing?" onKeyDown={(e) => e.key === "Enter" && addTask()} />
              <Button size="sm" onClick={addTask} disabled={busy || !taskTitle.trim()}>
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          {/* Timeline */}
          <div>
            <div className="mb-2 text-xs font-medium text-muted-foreground">Activity</div>
            {isLoading ? (
              <div className="text-sm text-muted-foreground">Loading…</div>
            ) : (timeline ?? []).length === 0 ? (
              <div className="text-sm text-muted-foreground">No activity yet.</div>
            ) : (
              <ul className="space-y-3">
                {(timeline ?? []).map((item) => (
                  <TimelineRow key={`${item.kind}-${item.id}`} item={item} />
                ))}
              </ul>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}

function TimelineRow({ item }: { item: TimelineItem }) {
  let Icon: React.ElementType = StickyNote;
  let tint = "text-muted-foreground";
  if (item.kind === "message") {
    Icon = item.channel ? CHANNEL_ICON[item.channel] ?? Mail : Mail;
    tint = item.direction === "inbound" ? "text-success" : "text-primary";
  } else if (item.kind === "task") {
    Icon = item.channel === "meeting" ? Calendar : CheckSquare;
    tint = "text-amber-500";
  }
  return (
    <li className="flex gap-3">
      <div className="mt-0.5">
        <Icon className={`h-4 w-4 shrink-0 ${tint}`} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">
            {item.kind === "message"
              ? item.title
              : item.kind === "note"
              ? "Note"
              : item.title}
          </span>
          {item.kind === "message" && item.direction === "inbound" && (
            <Badge variant="success" className="gap-1 text-[10px]"><CornerUpLeft className="h-2.5 w-2.5" /> reply</Badge>
          )}
          {item.kind === "task" && item.status && (
            <Badge variant={item.status === "done" ? "success" : "secondary"} className="text-[10px]">{item.status}</Badge>
          )}
          <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{formatDate(item.at)}</span>
        </div>
        {item.body && <p className="mt-0.5 whitespace-pre-wrap text-sm text-muted-foreground">{item.body}</p>}
        {item.actor && <p className="mt-0.5 text-[11px] text-muted-foreground">— {item.actor}</p>}
      </div>
    </li>
  );
}
