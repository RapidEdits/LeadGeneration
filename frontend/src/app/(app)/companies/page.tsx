"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Plus, Search, Globe, MapPin, Users } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { api, ApiError } from "@/lib/api";

export default function CompaniesPage() {
  const qc = useQueryClient();
  const [search, setSearch] = React.useState("");
  const [debounced, setDebounced] = React.useState("");

  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ["companies", debounced],
    queryFn: () => api.listCompanies(debounced || undefined),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["companies"] });
  const companies = data ?? [];

  return (
    <div>
      <PageHeader title="Companies" description="Accounts your leads belong to">
        <AddCompanyDialog onCreated={invalidate} />
      </PageHeader>

      <div className="relative mb-4 max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search companies…" className="pl-9" />
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-32 rounded-xl" />)}
        </div>
      ) : companies.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed py-16 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent">
            <Building2 className="h-6 w-6 text-accent-foreground" />
          </div>
          <div>
            <p className="font-medium">No companies yet</p>
            <p className="text-sm text-muted-foreground">Add a company to group and enrich your leads.</p>
          </div>
          <AddCompanyDialog onCreated={invalidate} />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {companies.map((c) => (
            <Card key={c.id} className="transition-shadow hover:shadow-md">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-start justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent font-semibold text-accent-foreground">
                    {c.name[0]?.toUpperCase()}
                  </div>
                  <Badge variant="secondary" className="gap-1">
                    <Users className="h-3 w-3" /> {c.lead_count}
                  </Badge>
                </div>
                <div>
                  <div className="font-medium">{c.name}</div>
                  {c.industry && <div className="text-sm text-muted-foreground">{c.industry}</div>}
                </div>
                <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                  {c.domain && <span className="flex items-center gap-1"><Globe className="h-3 w-3" />{c.domain}</span>}
                  {c.location && <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{c.location}</span>}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function AddCompanyDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [form, setForm] = React.useState({ name: "", domain: "", industry: "", location: "", website: "" });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setBusy(true);
    try {
      await api.createCompany(Object.fromEntries(Object.entries(form).filter(([, v]) => v)) as never);
      toast.success("Company added");
      setForm({ name: "", domain: "", industry: "", location: "", website: "" });
      setOpen(false);
      onCreated();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not add company");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button><Plus className="h-4 w-4" /> Add company</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Add a company</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="cn">Company name</Label>
            <Input id="cn" required value={form.name} onChange={set("name")} placeholder="Acme Inc." />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2"><Label htmlFor="cd">Domain</Label>
              <Input id="cd" value={form.domain} onChange={set("domain")} placeholder="acme.com" /></div>
            <div className="space-y-2"><Label htmlFor="ci">Industry</Label>
              <Input id="ci" value={form.industry} onChange={set("industry")} placeholder="SaaS" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2"><Label htmlFor="cl">Location</Label>
              <Input id="cl" value={form.location} onChange={set("location")} placeholder="New York" /></div>
            <div className="space-y-2"><Label htmlFor="cw">Website</Label>
              <Input id="cw" value={form.website} onChange={set("website")} placeholder="https://acme.com" /></div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Adding…" : "Add company"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
