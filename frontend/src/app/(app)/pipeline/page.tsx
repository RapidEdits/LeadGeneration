"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { KanbanSquare, Building2, CheckSquare } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { api, ApiError } from "@/lib/api";
import { initials } from "@/lib/utils";
import { LeadDetailDrawer } from "@/components/lead-detail";
import type { LeadStatus, PipelineCard } from "@/lib/types";

const STAGE_ACCENT: Record<string, string> = {
  new: "border-t-slate-400", enriched: "border-t-sky-400", qualified: "border-t-violet-500",
  contacted: "border-t-blue-500", replied: "border-t-emerald-500", won: "border-t-green-600",
  lost: "border-t-rose-500", disqualified: "border-t-zinc-500",
};

export default function PipelinePage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["pipeline"], queryFn: () => api.pipeline() });
  const [openLead, setOpenLead] = React.useState<string | null>(null);
  const [dragId, setDragId] = React.useState<string | null>(null);
  const [overStage, setOverStage] = React.useState<string | null>(null);

  const stages = data?.stages ?? [];

  const move = async (leadId: string, to: LeadStatus, from: LeadStatus) => {
    if (to === from) return;
    // Optimistic: move the card between columns immediately.
    qc.setQueryData(["pipeline"], (prev: typeof data) => {
      if (!prev) return prev;
      let moved: PipelineCard | undefined;
      const stages2 = prev.stages.map((s) => {
        if (s.status === from) {
          moved = s.cards.find((c) => c.id === leadId);
          return { ...s, count: s.count - 1, cards: s.cards.filter((c) => c.id !== leadId) };
        }
        return s;
      });
      return {
        stages: stages2.map((s) =>
          s.status === to && moved
            ? { ...s, count: s.count + 1, cards: [{ ...moved, status: to }, ...s.cards] }
            : s,
        ),
      };
    });
    try {
      await api.updateLead(leadId, { status: to });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not move lead");
      qc.invalidateQueries({ queryKey: ["pipeline"] });
    }
  };

  return (
    <div>
      <PageHeader title="Pipeline" description="Drag leads across stages. Click a card to see the full history." />

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-4">
          {stages.map((stage) => (
            <div
              key={stage.status}
              onDragOver={(e) => {
                e.preventDefault();
                setOverStage(stage.status);
              }}
              onDragLeave={() => setOverStage((s) => (s === stage.status ? null : s))}
              onDrop={() => {
                if (dragId) {
                  const from = stages.find((s) => s.cards.some((c) => c.id === dragId))?.status;
                  if (from) move(dragId, stage.status, from);
                }
                setDragId(null);
                setOverStage(null);
              }}
              className={
                "flex max-h-[calc(100vh-12rem)] w-72 shrink-0 flex-col rounded-lg border bg-muted/30 " +
                (overStage === stage.status ? "ring-2 ring-primary/40" : "")
              }
            >
              <div className={"flex items-center justify-between border-t-2 px-3 py-2 " + (STAGE_ACCENT[stage.status] ?? "border-t-slate-400")}>
                <span className="text-sm font-semibold">{stage.label}</span>
                <Badge variant="secondary">{stage.count}</Badge>
              </div>
              <div className="flex-1 space-y-2 overflow-y-auto p-2">
                {stage.cards.length === 0 ? (
                  <p className="px-1 py-6 text-center text-xs text-muted-foreground">No leads</p>
                ) : (
                  stage.cards.map((card) => (
                    <article
                      key={card.id}
                      draggable
                      onDragStart={() => setDragId(card.id)}
                      onDragEnd={() => setDragId(null)}
                      onClick={() => setOpenLead(card.id)}
                      className={
                        "cursor-pointer rounded-md border bg-background p-2.5 shadow-sm transition hover:border-primary/50 " +
                        (dragId === card.id ? "opacity-40" : "")
                      }
                    >
                      <div className="flex items-center gap-2">
                        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-[11px] font-medium">
                          {initials(card.full_name)}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium">{card.full_name || "Unnamed"}</div>
                          {card.title && <div className="truncate text-xs text-muted-foreground">{card.title}</div>}
                        </div>
                        {typeof card.score === "number" && (
                          <Badge variant="outline" className="text-[10px]">{Math.round(card.score)}</Badge>
                        )}
                      </div>
                      <div className="mt-1.5 flex items-center gap-3 text-[11px] text-muted-foreground">
                        {card.company_name && (
                          <span className="flex min-w-0 items-center gap-1">
                            <Building2 className="h-3 w-3 shrink-0" />
                            <span className="truncate">{card.company_name}</span>
                          </span>
                        )}
                        {card.open_tasks > 0 && (
                          <span className="ml-auto flex items-center gap-1 text-amber-600">
                            <CheckSquare className="h-3 w-3" /> {card.open_tasks}
                          </span>
                        )}
                      </div>
                    </article>
                  ))
                )}
              </div>
            </div>
          ))}
          {stages.length === 0 && (
            <div className="flex w-full flex-col items-center gap-3 py-16 text-center text-sm text-muted-foreground">
              <KanbanSquare className="h-8 w-8" />
              Import or add leads to populate your pipeline.
            </div>
          )}
        </div>
      )}

      <LeadDetailDrawer leadId={openLead} onClose={() => setOpenLead(null)} />
    </div>
  );
}
