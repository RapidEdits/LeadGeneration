"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Search, Upload, Plus, Trash2, Users, Linkedin, ChevronLeft, ChevronRight, AlertCircle,
  Sparkles, Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/status-badge";
import { ImportWizard } from "@/components/import-wizard";
import { AddLeadDialog } from "@/components/add-lead-dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import type { LeadFilter, LeadStatus } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const STATUSES: (LeadStatus | "all")[] = [
  "all", "new", "enriched", "qualified", "contacted", "replied", "won", "lost", "disqualified",
];
const PAGE_SIZE = 25;

export default function LeadsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [status, setStatus] = React.useState<LeadStatus | "all">("all");
  const [page, setPage] = React.useState(1);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [importOpen, setImportOpen] = React.useState(false);
  const [qualifying, setQualifying] = React.useState(false);

  React.useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const filter: LeadFilter = React.useMemo(() => ({
    search: debounced || undefined,
    conditions: status === "all" ? [] : [{ field: "status", op: "eq", value: status }],
    page,
    page_size: PAGE_SIZE,
    sort_by: "created_at",
    sort_dir: "desc",
  }), [debounced, status, page]);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["leads", filter],
    queryFn: () => api.searchLeads(filter),
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const invalidate = () => qc.invalidateQueries({ queryKey: ["leads"] });

  const toggleAll = () => {
    setSelected((prev) =>
      prev.size === items.length ? new Set() : new Set(items.map((l) => l.id)),
    );
  };
  const toggle = (id: string) =>
    setSelected((prev) => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const bulkDelete = async () => {
    const ids = [...selected];
    try {
      await api.bulkLeads({ lead_ids: ids, action: "delete" });
      toast.success(`${ids.length} lead(s) deleted`);
      setSelected(new Set());
      invalidate();
    } catch {
      toast.error("Bulk delete failed");
    }
  };

  const bulkQualify = async () => {
    const ids = [...selected];
    setQualifying(true);
    try {
      const res = await api.aiQualifyBulk(ids);
      const scored = res.results.filter((r) => r.status === "ok").length;
      if (scored === 0) {
        toast.message("AI is disabled or returned no scores — set GEMINI_API_KEY to enable.");
      } else {
        toast.success(`Qualified ${scored} of ${res.processed} lead(s) with AI`);
      }
      setSelected(new Set());
      invalidate();
    } catch {
      toast.error("AI qualification failed");
    } finally {
      setQualifying(false);
    }
  };

  return (
    <div>
      <PageHeader title="Leads" description={`${total} lead${total === 1 ? "" : "s"} in this workspace`}>
        <Button variant="outline" onClick={() => setImportOpen(true)}>
          <Upload className="h-4 w-4" /> Import CSV
        </Button>
        <AddLeadDialog
          onCreated={invalidate}
          trigger={<Button><Plus className="h-4 w-4" /> Add lead</Button>}
        />
      </PageHeader>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, email, title, location…"
            className="pl-9"
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => { setStatus(s); setPage(1); }}
              className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                status === s ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {selected.size > 0 && (
        <div className="mb-3 flex items-center justify-between rounded-lg border bg-accent/50 px-4 py-2 text-sm">
          <span>{selected.size} selected</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={bulkQualify} disabled={qualifying}>
              {qualifying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Qualify with AI
            </Button>
            <Button size="sm" variant="destructive" onClick={bulkDelete}>
              <Trash2 className="h-4 w-4" /> Delete
            </Button>
          </div>
        </div>
      )}

      <div className="rounded-xl border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[hsl(var(--primary))]"
                  checked={items.length > 0 && selected.size === items.length}
                  onChange={toggleAll}
                  aria-label="Select all"
                />
              </TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>Score</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Added</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 8 }).map((__, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && isError && (
              <TableRow>
                <TableCell colSpan={8}>
                  <div className="flex flex-col items-center gap-2 py-12 text-center">
                    <AlertCircle className="h-8 w-8 text-destructive" />
                    <p className="text-sm text-muted-foreground">Couldn't load leads.</p>
                    <Button size="sm" variant="outline" onClick={() => refetch()}>Retry</Button>
                  </div>
                </TableCell>
              </TableRow>
            )}

            {!isLoading && !isError && items.length === 0 && (
              <TableRow>
                <TableCell colSpan={8}>
                  <div className="flex flex-col items-center gap-3 py-16 text-center">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent">
                      <Users className="h-6 w-6 text-accent-foreground" />
                    </div>
                    <div>
                      <p className="font-medium">No leads yet</p>
                      <p className="text-sm text-muted-foreground">Import a CSV or add your first lead.</p>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" onClick={() => setImportOpen(true)}>
                        <Upload className="h-4 w-4" /> Import CSV
                      </Button>
                      <AddLeadDialog onCreated={invalidate} trigger={<Button><Plus className="h-4 w-4" /> Add lead</Button>} />
                    </div>
                  </div>
                </TableCell>
              </TableRow>
            )}

            {!isLoading && !isError &&
              items.map((lead) => (
                <TableRow key={lead.id} data-state={selected.has(lead.id) ? "selected" : undefined}>
                  <TableCell>
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-[hsl(var(--primary))]"
                      checked={selected.has(lead.id)}
                      onChange={() => toggle(lead.id)}
                      aria-label={`Select ${lead.full_name}`}
                    />
                  </TableCell>
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-2">
                      {lead.full_name || "—"}
                      {lead.linkedin_url && <Linkedin className="h-3.5 w-3.5 text-muted-foreground" />}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{lead.title || "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{lead.location || "—"}</TableCell>
                  <TableCell>
                    {lead.score != null ? <Badge variant="secondary">{Math.round(lead.score)}</Badge> : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{lead.email || "—"}</TableCell>
                  <TableCell><StatusBadge status={lead.status} /></TableCell>
                  <TableCell className="text-muted-foreground">{formatDate(lead.created_at)}</TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
          <span>Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft className="h-4 w-4" /> Prev
            </Button>
            <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <ImportWizard open={importOpen} onOpenChange={setImportOpen} onImported={invalidate} />
    </div>
  );
}
