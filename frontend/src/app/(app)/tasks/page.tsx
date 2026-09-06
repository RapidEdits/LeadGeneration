"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckSquare, Square, Plus, Phone, Mail, Calendar, Linkedin, ListTodo, Trash2, Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn, formatDate } from "@/lib/utils";
import { api, ApiError } from "@/lib/api";
import { LeadDetailDrawer } from "@/components/lead-detail";
import type { Task, TaskType } from "@/lib/types";

const SCOPES = [
  { id: "open", label: "Open" },
  { id: "overdue", label: "Overdue" },
  { id: "upcoming", label: "Upcoming" },
  { id: "done", label: "Done" },
] as const;

const TYPE_ICON: Record<TaskType, React.ElementType> = {
  todo: ListTodo, call: Phone, email: Mail, meeting: Calendar, linkedin: Linkedin,
};

export default function TasksPage() {
  const qc = useQueryClient();
  const [scope, setScope] = React.useState<(typeof SCOPES)[number]["id"]>("open");
  const { data, isLoading } = useQuery({
    queryKey: ["tasks", scope],
    queryFn: () => api.tasks(scope),
    refetchInterval: 20000,
  });
  const [title, setTitle] = React.useState("");
  const [type, setType] = React.useState<TaskType>("todo");
  const [due, setDue] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [openLead, setOpenLead] = React.useState<string | null>(null);

  const tasks = data ?? [];
  const refresh = () => qc.invalidateQueries({ queryKey: ["tasks"] });

  const create = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await api.createTask({ title: title.trim(), type, due_at: due ? new Date(due).toISOString() : null });
      setTitle(""); setDue("");
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not add task");
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (t: Task) => {
    try {
      if (t.status === "done") await api.updateTask(t.id, { status: "open" });
      else await api.completeTask(t.id);
      refresh();
    } catch {
      toast.error("Could not update task");
    }
  };

  const remove = async (t: Task) => {
    try {
      await api.deleteTask(t.id);
      refresh();
    } catch {
      toast.error("Could not delete task");
    }
  };

  const overdue = (t: Task) =>
    t.status === "open" && t.due_at && new Date(t.due_at) < new Date();

  return (
    <div>
      <PageHeader title="Tasks" description="Calls, emails, meetings and to-dos across your pipeline" />

      {/* Quick add */}
      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border p-2">
        <select value={type} onChange={(e) => setType(e.target.value as TaskType)}
          className="rounded-md border border-input bg-background px-2 py-2 text-sm">
          <option value="todo">To-do</option>
          <option value="call">Call</option>
          <option value="email">Email</option>
          <option value="meeting">Meeting</option>
          <option value="linkedin">LinkedIn</option>
        </select>
        <Input className="min-w-[200px] flex-1" placeholder="Add a task…" value={title}
          onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()} />
        <Input type="datetime-local" className="w-auto" value={due} onChange={(e) => setDue(e.target.value)} />
        <Button onClick={create} disabled={busy || !title.trim()}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Add
        </Button>
      </div>

      {/* Scope tabs */}
      <div className="mb-3 flex gap-1">
        {SCOPES.map((s) => (
          <button key={s.id} onClick={() => setScope(s.id)}
            className={cn("rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              scope === s.id ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/60")}>
            {s.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : tasks.length === 0 ? (
        <div className="rounded-lg border py-16 text-center text-sm text-muted-foreground">
          Nothing here. Add a task above or from a lead&apos;s detail panel.
        </div>
      ) : (
        <ul className="divide-y rounded-lg border">
          {tasks.map((t) => {
            const Icon = TYPE_ICON[t.type] ?? ListTodo;
            return (
              <li key={t.id} className="flex items-center gap-3 px-4 py-3">
                <button onClick={() => toggle(t)} className="shrink-0 text-muted-foreground hover:text-foreground">
                  {t.status === "done" ? <CheckSquare className="h-5 w-5 text-success" /> : <Square className="h-5 w-5" />}
                </button>
                <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className={cn("truncate text-sm", t.status === "done" && "text-muted-foreground line-through")}>
                    {t.title}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {t.lead_name && (
                      <button className="hover:underline" onClick={() => t.lead_id && setOpenLead(t.lead_id)}>
                        {t.lead_name}
                      </button>
                    )}
                    {t.due_at && (
                      <span className={cn(overdue(t) && "font-medium text-rose-500")}>
                        {overdue(t) ? "Overdue · " : "Due "}{formatDate(t.due_at)}
                      </span>
                    )}
                    {t.assignee_name && <span>· {t.assignee_name}</span>}
                  </div>
                </div>
                <Badge variant="outline" className="text-[10px] capitalize">{t.type}</Badge>
                <Button variant="ghost" size="icon" onClick={() => remove(t)}>
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </li>
            );
          })}
        </ul>
      )}

      <LeadDetailDrawer leadId={openLead} onClose={() => setOpenLead(null)} />
    </div>
  );
}
