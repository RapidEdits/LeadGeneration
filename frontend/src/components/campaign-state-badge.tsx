import { Badge } from "@/components/ui/badge";
import type { CampaignState } from "@/lib/types";

const MAP: Record<CampaignState, { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline" }> = {
  draft: { label: "Draft", variant: "secondary" },
  scheduled: { label: "Scheduled", variant: "default" },
  active: { label: "Active", variant: "success" },
  paused: { label: "Paused", variant: "warning" },
  completed: { label: "Completed", variant: "default" },
  archived: { label: "Archived", variant: "outline" },
};

export function CampaignStateBadge({ state }: { state: CampaignState }) {
  const s = MAP[state] ?? MAP.draft;
  return <Badge variant={s.variant}>{s.label}</Badge>;
}
