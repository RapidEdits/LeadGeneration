import { Badge } from "@/components/ui/badge";
import type { LeadStatus } from "@/lib/types";

const MAP: Record<LeadStatus, { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline" }> = {
  new: { label: "New", variant: "secondary" },
  enriched: { label: "Enriched", variant: "default" },
  qualified: { label: "Qualified", variant: "default" },
  contacted: { label: "Contacted", variant: "warning" },
  replied: { label: "Replied", variant: "success" },
  won: { label: "Won", variant: "success" },
  lost: { label: "Lost", variant: "destructive" },
  disqualified: { label: "Disqualified", variant: "outline" },
};

export function StatusBadge({ status }: { status: LeadStatus }) {
  const s = MAP[status] ?? MAP.new;
  return <Badge variant={s.variant}>{s.label}</Badge>;
}
