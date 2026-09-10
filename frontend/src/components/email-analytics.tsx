"use client";
import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const labels: Record<string, string> = { sent: "Accepted by provider", delivered: "Confirmed delivered", opened: "Unique opens",
  clicked: "Unique clicks", replied: "Emails with replies", bounced: "Bounced", failed: "Failed attempts", queued: "Queued", simulated: "Simulated", unsubscribed: "Unsubscribed" };
const colors = { sent: "#3b82f6", opened: "#8b5cf6", clicked: "#f59e0b", replied: "#10b981" };

export function EmailAnalytics({ campaignId }: { campaignId?: string }) {
  const [selected, setSelected] = React.useState("");
  const [days, setDays] = React.useState(30);
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: api.listCampaigns, enabled: !campaignId });
  const id = campaignId || selected || undefined;
  const report = useQuery({ queryKey: ["email-metrics", days, id], queryFn: () => api.emailMetrics(days, id), refetchInterval: 15000 });
  const data = report.data;
  const [hover, setHover] = React.useState<number | null>(null);
  const keys = Object.keys(colors) as (keyof typeof colors)[];
  const max = Math.max(1, ...(data?.points.flatMap(p => keys.map(k => Number(p[k]))) ?? []));
  const n = data?.points.length ?? 1;
  const x = (i: number) => 44 + i * 690 / Math.max(1, n - 1);
  const y = (v: number) => 172 - v * 145 / max;

  return <Card className="mb-6"><CardHeader><div className="flex flex-wrap justify-between gap-3"><div><CardTitle>Email campaign insights</CardTitle><CardDescription>Real sending outcomes and engagement, organized by campaign.</CardDescription></div>
    <div className="flex flex-wrap gap-2">{!campaignId && <select aria-label="Analytics campaign" value={selected} onChange={e => { setSelected(e.target.value); setHover(null); }} className="max-w-72 rounded-md border bg-background px-3 py-2 text-sm"><option value="">All campaigns</option>{campaigns.data?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>}
      <select aria-label="Analytics date range" value={days} onChange={e => { setDays(Number(e.target.value)); setHover(null); }} className="rounded-md border bg-background px-3 py-2 text-sm">{[7, 30, 90, 180].map(d => <option key={d} value={d}>{d} days</option>)}</select>
      <Button variant="outline" asChild><Link href={`/inbox${id ? `?campaign=${encodeURIComponent(id)}` : ""}`}>View campaign mail</Link></Button>
    </div></div></CardHeader><CardContent className="space-y-6">
    {report.isLoading && <p role="status" className="text-sm text-muted-foreground">Loading email insights…</p>}
    {report.isError && <p role="alert" className="text-sm text-destructive">Could not load email insights: {report.error.message}</p>}
    {data && <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">{Object.entries(labels).map(([key, label]) => <div key={key} className="rounded-lg border p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{data.totals[key] ?? 0}</p></div>)}</div>
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div><h3 className="mb-2 text-sm font-medium">Email cohorts by creation date (UTC)</h3>
          <svg viewBox="0 0 760 210" role="img" aria-label="Daily email sends and unique engagement chart" className="w-full" onMouseLeave={() => setHover(null)}>
            {[0, 0.5, 1].map(f => <g key={f}><line x1="44" x2="734" y1={y(max * f)} y2={y(max * f)} stroke="currentColor" opacity="0.12" /><text x="35" y={y(max * f) + 4} textAnchor="end" fontSize="10" fill="currentColor">{Math.round(max * f)}</text></g>)}
            {keys.map(key => <polyline key={key} fill="none" stroke={colors[key]} strokeWidth="2.5" points={data.points.map((p, i) => `${x(i)},${y(Number(p[key]))}`).join(" ")} />)}
            {data.points.map((p, i) => <rect key={p.date} x={x(i) - 690 / n / 2} y="20" width={690 / n} height="155" fill="transparent" onMouseEnter={() => setHover(i)}><title>{p.date}: {keys.map(k => `${labels[k]} ${p[k]}`).join(", ")}</title></rect>)}
            {hover !== null && <line x1={x(hover)} x2={x(hover)} y1="20" y2="178" stroke="currentColor" opacity="0.3" strokeDasharray="3 3" />}
            <text x="44" y="201" fontSize="11" fill="currentColor">{data.points[0]?.date}</text><text x="734" y="201" textAnchor="end" fontSize="11" fill="currentColor">{data.points[n - 1]?.date}</text>
          </svg>
          <div className="flex flex-wrap gap-3 text-xs">{keys.map(k => <span key={k} className="flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: colors[k] }} />{labels[k]}{hover !== null ? `: ${data.points[hover]?.[k] ?? 0}` : ""}</span>)}</div>
          {data.totals.sent === 0 && <p className="mt-3 text-sm text-muted-foreground">No real email sends in this window. Simulated mail is listed separately above.</p>}
        </div>
        <div className="space-y-4"><h3 className="text-sm font-medium">Engagement rates</h3>{([ ["opened_rate", "Open rate"], ["clicked_rate", "Click rate"], ["replied_rate", "Reply rate"], ["bounce_rate", "Bounce rate"] ] as const).map(([key, label]) => <div key={key}>
          <div className="mb-1 flex justify-between text-xs"><span>{label}</span><span>{((data.rates[key] ?? 0) * 100).toFixed(1)}%</span></div><div className="h-2 rounded-full bg-accent"><div className="h-2 rounded-full bg-primary" style={{ width: `${Math.min(100, (data.rates[key] ?? 0) * 100)}%` }} /></div>
        </div>)}</div>
      </div>
      <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Measurement notes & daily data</summary><p className="my-3">{data.definition} Bounce rate uses attempted emails; engagement rates use accepted emails. Daily engagement is attributed to the email's creation date.</p><div className="max-h-64 overflow-auto"><table className="w-full text-left"><caption className="sr-only">Daily email metrics</caption><thead><tr><th>Date (UTC)</th>{keys.map(k => <th key={k}>{labels[k]}</th>)}</tr></thead><tbody>{data.points.map(p => <tr key={p.date}><td className="py-1">{p.date}</td>{keys.map(k => <td key={k}>{p[k]}</td>)}</tr>)}</tbody></table></div></details>
    </>}
  </CardContent></Card>;
}
