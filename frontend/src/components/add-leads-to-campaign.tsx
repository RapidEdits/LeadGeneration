"use client";
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, UserPlus } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";

export function AddLeadsToCampaign({
  campaignId, onAdded, trigger,
}: { campaignId: string; onAdded: () => void; trigger: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [busy, setBusy] = React.useState(false);

  const { data } = useQuery({
    queryKey: ["leads-picker", search, open],
    queryFn: () => api.searchLeads({ search: search || undefined, page_size: 50 }),
    enabled: open,
  });
  const leads = data?.items ?? [];

  const toggle = (id: string) =>
    setSelected((p) => {
      const n = new Set(p);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const add = async () => {
    if (selected.size === 0) return;
    setBusy(true);
    try {
      const res = await api.addCampaignLeads(campaignId, [...selected]);
      toast.success(`${res.added} lead(s) added`);
      setSelected(new Set());
      setOpen(false);
      onAdded();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not add leads");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setSelected(new Set()); }}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Add leads to campaign</DialogTitle></DialogHeader>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search leads…" className="pl-9" />
        </div>
        <div className="max-h-72 space-y-1 overflow-y-auto">
          {leads.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">No leads found.</p>}
          {leads.map((l) => (
            <label key={l.id} className="flex cursor-pointer items-center gap-3 rounded-md border p-2 text-sm hover:bg-accent/50">
              <input type="checkbox" className="h-4 w-4 accent-[hsl(var(--primary))]"
                checked={selected.has(l.id)} onChange={() => toggle(l.id)} />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{l.full_name || "—"}</div>
                <div className="truncate text-xs text-muted-foreground">{l.email || "no email"}</div>
              </div>
            </label>
          ))}
        </div>
        <DialogFooter>
          <span className="mr-auto self-center text-sm text-muted-foreground">{selected.size} selected</span>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={add} disabled={busy || selected.size === 0}>
            <UserPlus className="h-4 w-4" /> Add {selected.size > 0 ? selected.size : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
