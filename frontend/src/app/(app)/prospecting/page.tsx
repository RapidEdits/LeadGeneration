"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, Globe2, MapPin, ArrowRight, Loader2, Save, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import type { ProductProfile } from "@/lib/types";

const empty: ProductProfile = { name: "", overview: "", website: "", target_customer: "", locations: [],
  country_code: "ALL", max_leads: 25, radius_km: null, latitude: null, longitude: null };
const control = "w-full rounded-md border bg-background px-3 py-2 text-sm";

export default function ProspectingPage() {
  const qc = useQueryClient(), router = useRouter();
  const saved = useQuery({ queryKey: ["product-profile"], queryFn: api.productProfile });
  const runs = useQuery({ queryKey: ["discovery-runs"], queryFn: api.discoveryRuns, refetchInterval: 4000 });
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: api.listCampaigns });
  const [profile, setProfile] = React.useState<ProductProfile>(empty);
  const [locationText, setLocationText] = React.useState("");
  const loaded = React.useRef(false);
  React.useEffect(() => {
    if (saved.data?.profile && !loaded.current) {
      setProfile(saved.data.profile); setLocationText(saved.data.profile.locations.join("; ")); loaded.current = true;
    }
  }, [saved.data]);
  const [mode, setMode] = React.useState<"search" | "websites">("search");
  const [sites, setSites] = React.useState("");
  const [key, setKey] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const [runId, setRunId] = React.useState("");
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [destination, setDestination] = React.useState("leads");
  const [subject, setSubject] = React.useState("");
  const [body, setBody] = React.useState("");
  const [campaignName, setCampaignName] = React.useState("");
  const run = runs.data?.find(r => r.id === runId) ?? runs.data?.[0];
  const running = runs.data?.some(r => ["queued", "running"].includes(r.status));
  const update = <K extends keyof ProductProfile>(k: K, v: ProductProfile[K]) => setProfile(p => ({ ...p, [k]: v }));
  const perform = async (label: string, action: () => Promise<void>) => {
    setBusy(label);
    try { await action(); } catch (err) { toast.error(err instanceof Error ? err.message : "Something went wrong"); }
    finally { setBusy(""); }
  };
  const save = async () => {
    await api.saveProductProfile({ ...profile, locations: locationText.split(";").map(s => s.trim()).filter(Boolean) });
    await qc.invalidateQueries({ queryKey: ["product-profile"] });
  };
  const search = () => perform("search", async () => {
    await save();
    const result = await api.discover(mode, mode === "websites" ? sites.split(/\n/).map(s => s.trim()).filter(Boolean) : []);
    setRunId(result.id); setSelected(new Set());
    await qc.invalidateQueries({ queryKey: ["discovery-runs"] });
    toast.success("Discovery queued. Results will appear here as websites are checked.");
  });
  const importSelected = () => perform("import", async () => {
    if (!run) return;
    let campaignId = destination === "leads" ? undefined : destination;
    if (destination === "new") {
      const campaign = await api.createCampaign({ name: campaignName || `${profile.name} outreach`,
        description: `${profile.overview}\nProduct website: ${profile.website}`, test_mode: true, approval_mode: "auto",
        channels: { email: { enabled: true, daily_limit: 50 } },
        steps: [{ channel: "email", delay_days: 0, subject, body_template: body, enabled: true }],
      });
      campaignId = campaign.id;
      setDestination(campaign.id);
      await qc.invalidateQueries({ queryKey: ["campaigns"] });
    }
    const result = await api.importProspects(run.id, [...selected], campaignId);
    toast.success(`${result.created} new leads · ${result.duplicates} existing · ${result.suppressed} suppressed · ${result.added} added to campaign`);
    setSelected(new Set());
    await qc.invalidateQueries({ queryKey: ["discovery-runs"] });
    await qc.invalidateQueries({ queryKey: ["leads"] });
    if (campaignId) router.push(`/campaigns/${campaignId}`);
  });

  return <div className="space-y-6">
    <PageHeader title="Find your next customers" description="Tell us what you sell. Discover relevant businesses, review the evidence, and build your next campaign." />
    <div className="grid gap-3 sm:grid-cols-3">
      {[ [Globe2, "1. Describe your product", "Product, ideal customer and geography"], [Search, "2. Discover & review", "Public contact details with source evidence"], [ArrowRight, "3. Start a campaign", "Review your email, then launch outreach"] ].map(([Icon, title, hint]) => {
        const I = Icon as React.ElementType;
        return <div key={String(title)} className="flex items-center gap-3 rounded-lg border bg-card p-4"><I className="h-5 w-5 text-primary" /><div><p className="text-sm font-medium">{String(title)}</p><p className="text-xs text-muted-foreground">{String(hint)}</p></div></div>;
      })}
    </div>
    {(saved.isError || runs.isError) && <p role="alert" className="text-sm text-destructive">Unable to load prospecting. {String((saved.error ?? runs.error)?.message)}</p>}
    <div className="grid items-start gap-6 xl:grid-cols-[1fr_1fr]">
      <Card><CardHeader><CardTitle>Product & ideal customer</CardTitle><CardDescription>Your saved brief guides every search.</CardDescription></CardHeader>
        <CardContent><form id="product-form" className="space-y-4" onSubmit={e => { e.preventDefault(); search(); }}>
          <label className="block text-sm">Product name<Input required maxLength={255} value={profile.name} onChange={e => update("name", e.target.value)} placeholder="Your SaaS product" /></label>
          <label className="block text-sm">Product website<Input required type="url" value={profile.website} onChange={e => update("website", e.target.value)} placeholder="https://yourproduct.com" /></label>
          <label className="block text-sm">What problem does it solve?<textarea required minLength={20} maxLength={6000} rows={4} className={control} value={profile.overview} onChange={e => update("overview", e.target.value)} placeholder="Explain who benefits, the problem you solve, and your key features." /></label>
          <label className="block text-sm">Who are your ideal customers?<Input required minLength={3} maxLength={300} value={profile.target_customer} onChange={e => update("target_customer", e.target.value)} placeholder="e.g. dental clinics, architecture firms, ecommerce retailers" /></label>
          <label className="block text-sm">Target locations <span className="text-muted-foreground">(separate up to five with ;)</span><Input required value={locationText} onChange={e => setLocationText(e.target.value)} placeholder="Mumbai; Pune; Bengaluru" /></label>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm">Search country code<Input maxLength={3} value={profile.country_code} onChange={e => update("country_code", e.target.value.toUpperCase())} placeholder="ALL or IN, US, GB…" /></label>
            <label className="text-sm">Maximum leads<Input type="number" min={1} max={100} value={profile.max_leads} onChange={e => update("max_leads", Number(e.target.value))} /></label>
          </div>
          <details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm font-medium"><MapPin className="mr-1 inline h-4 w-4" /> Optional radius targeting</summary>
            <p className="my-2 text-xs text-muted-foreground">Search near a coordinate. Only websites publishing coordinates inside this radius qualify; unknown locations are excluded.</p>
            <div className="grid grid-cols-3 gap-2">{([ ["latitude", "Latitude", -90, 90], ["longitude", "Longitude", -180, 180], ["radius_km", "Radius (km)", 0.1, 1000] ] as const).map(([field, label, min, max]) =>
              <label key={field} className="text-xs">{label}<Input type="number" step="any" min={min} max={max} value={profile[field] ?? ""} onChange={e => update(field, e.target.value ? Number(e.target.value) : null)} /></label>)}</div>
          </details>
          <Button type="button" variant="outline" disabled={!!busy || saved.isLoading} onClick={() => perform("save", async () => { await save(); toast.success("Product profile saved"); })}><Save className="h-4 w-4" /> Save profile</Button>
        </form></CardContent>
      </Card>
      <div className="space-y-5">
        <Card><CardHeader><CardTitle>Discovery sources</CardTitle><CardDescription>Find public business contacts from indexed websites.</CardDescription></CardHeader><CardContent className="space-y-4">
          <div className="flex gap-2">{(["search", "websites"] as const).map(m => <Button key={m} variant={mode === m ? "default" : "outline"} onClick={() => setMode(m)}>{m === "search" ? "Search the web" : "Supply websites"}</Button>)}</div>
          {mode === "search" ? <div className="space-y-3">
            <p className="text-sm text-muted-foreground">Searches your ideal customer and locations, then checks up to 40 business websites and their contact pages per run.</p>
            <Badge variant={saved.data?.search_configured ? "success" : "outline"}>{saved.data?.search_configured ? "Search connected" : "Search API key needed"}</Badge>
            <details><summary className="cursor-pointer text-sm text-primary">{saved.data?.search_configured ? "Update" : "Connect"} Brave Search</summary>
              <p className="my-2 text-xs text-muted-foreground">An admin can save a Brave Search API key here. The key is encrypted. Provider usage charges may apply.</p>
              <Input aria-label="Brave Search API key" type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} />
              <Button className="mt-2" variant="outline" disabled={!key.trim() || !!busy} onClick={() => perform("key", async () => { await save(); await api.saveSearchKey(key); setKey(""); await qc.invalidateQueries({ queryKey: ["product-profile"] }); toast.success("Search key saved"); })}>Save search key</Button>
            </details>
          </div> : <label className="block text-sm">Business websites to inspect<textarea rows={5} className={control} value={sites} onChange={e => setSites(e.target.value)} placeholder={"https://business-one.com\nhttps://business-two.com"} /><span className="text-xs text-muted-foreground">One URL per line, up to 40. Uses the same location and relevance checks. No search API key needed.</span></label>}
          <Button className="w-full" type="submit" form="product-form" disabled={!!busy || running || saved.isLoading || (mode === "search" && !saved.data?.search_configured) || (mode === "websites" && !sites.trim())}>
            {busy === "search" || running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}{running ? "Discovery in progress" : "Find matching leads"}
          </Button>
          <p className="text-xs text-muted-foreground">Results contain emails actually published on the business domain. Relevance and location are evidence to review, not a guarantee of fit or permission to contact.</p>
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Recent searches</CardTitle></CardHeader><CardContent className="max-h-72 space-y-2 overflow-auto">
          {!runs.data?.length && <p className="text-sm text-muted-foreground">Your searches and results will be saved here.</p>}
          {runs.data?.map(r => <button key={r.id} onClick={() => { setRunId(r.id); setSelected(new Set()); }} className={`w-full rounded-md border p-3 text-left text-sm ${run?.id === r.id ? "border-primary bg-accent/40" : ""}`}>
            <div className="flex justify-between gap-2"><span className="font-medium">{r.profile.name}</span><Badge variant="outline">{r.status}</Badge></div>
            <div className="mt-1 text-xs text-muted-foreground">{r.profile.locations.join(", ")} · {r.candidates.length} prospects · {new Date(r.created_at).toLocaleString()}</div>
          </button>)}
        </CardContent></Card>
      </div>
    </div>
    {run && <Card><CardHeader><CardTitle>Review prospects <span className="text-muted-foreground">/ {run.candidates.length}</span></CardTitle><CardDescription>{run.sites_scanned} / {run.sites_total} websites checked · {run.filtered} excluded by targeting</CardDescription></CardHeader><CardContent className="space-y-4">
      {["queued", "running"].includes(run.status) && <div role="status"><progress className="w-full accent-[hsl(var(--primary))]" value={run.sites_scanned} max={run.sites_total || 1} /><p className="text-sm text-muted-foreground">Checking public websites. You can leave this tab and return later.</p></div>}
      {run.error && <p role="alert" className="text-sm text-destructive">{run.error}</p>}
      {run.warnings.length > 0 && <details className="text-sm"><summary className="cursor-pointer text-amber-600">{run.warnings.length} discovery notes</summary><ul className="mt-2 max-h-40 overflow-auto text-xs text-muted-foreground">{run.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>}
      {run.status === "completed" && !run.candidates.length && <p className="py-8 text-center text-muted-foreground">No public contacts met these filters. Try broader customer keywords, a different location, or supply known business websites.</p>}
      {!!run.candidates.length && <>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selected.size === run.candidates.length} onChange={e => setSelected(new Set(e.target.checked ? run.candidates.map(c => c.id) : []))} /> Select all {run.candidates.length} prospects</label>
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b text-muted-foreground"><th className="p-2">Select</th><th>Business & public email</th><th>Location evidence</th><th>Fit evidence</th></tr></thead><tbody>
          {run.candidates.map(c => <tr key={c.id} className="border-b align-top"><td className="p-3"><input aria-label={`Select ${c.email}`} type="checkbox" checked={selected.has(c.id)} onChange={() => setSelected(p => { const next = new Set(p); next.has(c.id) ? next.delete(c.id) : next.add(c.id); return next; })} /></td>
            <td className="min-w-56 py-3 pr-4"><a href={c.website} target="_blank" rel="noreferrer" className="font-medium text-primary hover:underline">{c.company}</a><p>{c.email}</p><a href={c.source_url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">View email source ↗</a>{c.lead_id && <p className="flex items-center gap-1 text-xs text-emerald-600"><CheckCircle2 className="h-3 w-3" /> Imported</p>}</td>
            <td className="max-w-72 py-3 pr-4"><p className="font-medium">{c.location}</p><p className="text-xs text-muted-foreground">{c.location_evidence}</p><a href={c.location_source} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">Location source ↗</a></td>
            <td className="max-w-72 py-3"><Badge variant="outline">{c.score}% keyword match</Badge><p className="mt-1 text-xs text-muted-foreground">{c.reason}</p>{c.ai_score != null && <p className="mt-1 text-xs">AI fit: {c.ai_score}/100 · {c.ai_reason}</p>}</td>
          </tr>)}
        </tbody></table></div>
        <div className="rounded-lg bg-accent/40 p-4"><div className="flex flex-wrap items-end gap-3"><label className="min-w-60 flex-1 text-sm">Import destination<select aria-label="Import destination" className={control} value={destination} onChange={e => setDestination(e.target.value)}><option value="leads">Save to leads only</option><option value="new">Create a new email campaign</option>{campaigns.data?.filter(c => ["draft", "paused", "scheduled"].includes(c.state)).map(c => <option key={c.id} value={c.id}>{c.name} ({c.state})</option>)}</select></label>
          <Button disabled={!selected.size || !!busy || run.status !== "completed" || (destination === "new" && (!subject.trim() || !body.trim()))} onClick={importSelected}>{busy === "import" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />} Import {selected.size} selected</Button></div>
          {destination === "new" && <div className="mt-4 grid gap-3"><label className="text-sm">Campaign name<Input value={campaignName} onChange={e => setCampaignName(e.target.value)} placeholder={`${profile.name} outreach`} /></label><label className="text-sm">Email subject<Input value={subject} onChange={e => setSubject(e.target.value)} placeholder="A quick question for {{first_name}}" /></label><label className="text-sm">Email body<textarea rows={5} className={control} value={body} onChange={e => setBody(e.target.value)} placeholder="Hi {{first_name}}, …" /></label><p className="text-xs text-muted-foreground">Creates a draft with a 50-email daily limit and test mode on. Review the sequence, connect your email account in Settings, switch to live mode and launch when ready.</p></div>}
        </div>
      </>}
    </CardContent></Card>}
    <p className="text-sm text-muted-foreground">Already have a prospect list? <Link href="/leads" className="text-primary hover:underline">Import a CSV from Leads</Link>. Track your outreach in <Link href="/analytics" className="text-primary hover:underline">Analytics</Link>.</p>
  </div>;
}
