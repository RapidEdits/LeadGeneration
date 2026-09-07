"use client";
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Users, UserCheck, Send, MessageSquareReply, Trophy, Megaphone,
  Sparkles, Loader2, TrendingUp, AlertTriangle, CheckCircle2, Lightbulb,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import type { AIResult, TimeseriesPoint } from "@/lib/types";

const WINDOWS = [7, 30, 90] as const;
const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

function Metric({
  icon: Icon, label, value, hint, loading,
}: { icon: React.ElementType; label: string; value: React.ReactNode; hint?: string; loading?: boolean }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="text-sm text-muted-foreground">{label}</div>
          {loading ? <Skeleton className="mt-1 h-7 w-16" /> : <div className="text-2xl font-semibold">{value}</div>}
          {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
        </div>
      </CardContent>
    </Card>
  );
}

function Sparkline({ points }: { points: TimeseriesPoint[] }) {
  const W = 720, H = 140, pad = 6;
  if (points.length < 2) {
    return <div className="py-10 text-center text-sm text-muted-foreground">Not enough data yet.</div>;
  }
  const series: [keyof TimeseriesPoint, string][] = [
    ["messages_sent", "hsl(217 91% 60%)"],
    ["replies", "hsl(142 71% 45%)"],
    ["leads_created", "hsl(38 92% 50%)"],
  ];
  const max = Math.max(1, ...points.flatMap((p) => [p.messages_sent, p.replies, p.leads_created]));
  const x = (i: number) => pad + (i * (W - 2 * pad)) / (points.length - 1);
  const y = (v: number) => H - pad - (v * (H - 2 * pad)) / max;
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[520px]" preserveAspectRatio="none">
        {series.map(([key, color]) => (
          <polyline
            key={key} fill="none" stroke={color} strokeWidth={2}
            points={points.map((p, i) => `${x(i)},${y(p[key] as number)}`).join(" ")}
          />
        ))}
      </svg>
      <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: "hsl(217 91% 60%)" }} /> Sent</span>
        <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: "hsl(142 71% 45%)" }} /> Replies</span>
        <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: "hsl(38 92% 50%)" }} /> New leads</span>
      </div>
    </div>
  );
}

function InsightList({ title, items, icon: Icon, tone }: {
  title: string; items: unknown; icon: React.ElementType; tone: string;
}) {
  const list = Array.isArray(items) ? (items as string[]) : [];
  if (list.length === 0) return null;
  return (
    <div>
      <div className={`mb-1.5 flex items-center gap-1.5 text-sm font-medium ${tone}`}>
        <Icon className="h-4 w-4" /> {title}
      </div>
      <ul className="space-y-1 pl-5 text-sm">
        {list.map((t, i) => <li key={i} className="list-disc">{String(t)}</li>)}
      </ul>
    </div>
  );
}

export default function AnalyticsPage() {
  const [days, setDays] = React.useState<(typeof WINDOWS)[number]>(30);
  const overview = useQuery({ queryKey: ["an-overview", days], queryFn: () => api.analyticsOverview(days) });
  const funnel = useQuery({ queryKey: ["an-funnel"], queryFn: () => api.analyticsFunnel() });
  const outreach = useQuery({ queryKey: ["an-outreach", days], queryFn: () => api.analyticsOutreach(days) });
  const ts = useQuery({ queryKey: ["an-ts", days], queryFn: () => api.analyticsTimeseries(days) });
  const campaigns = useQuery({ queryKey: ["an-campaigns"], queryFn: () => api.analyticsCampaigns() });

  const [insight, setInsight] = React.useState<AIResult | null>(null);
  const [insightBusy, setInsightBusy] = React.useState(false);
  const runInsight = async () => {
    setInsightBusy(true);
    try {
      const r = await api.analyticsInsights(days);
      setInsight(r.result);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not generate insights");
    } finally {
      setInsightBusy(false);
    }
  };

  const o = overview.data;
  const topFunnel = funnel.data?.stages[0]?.count ?? 0;

  return (
    <div>
      <PageHeader title="Analytics" description="Funnel, outreach performance, and AI insights across your workspace">
        <div className="flex gap-1">
          {WINDOWS.map((w) => (
            <button key={w} onClick={() => setDays(w)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                days === w ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/60"
              }`}>
              {w}d
            </button>
          ))}
        </div>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric icon={Users} label="Total leads" value={o?.total_leads ?? 0}
          hint={o ? `+${o.new_leads} in ${days}d` : undefined} loading={overview.isLoading} />
        <Metric icon={UserCheck} label="Qualified" value={o?.qualified_leads ?? 0} loading={overview.isLoading} />
        <Metric icon={Send} label="Messages sent" value={o?.messages_sent ?? 0}
          hint={`last ${days} days`} loading={overview.isLoading} />
        <Metric icon={MessageSquareReply} label="Reply rate" value={o ? pct(o.reply_rate) : "—"}
          hint={o ? `${o.replies_received} replies` : undefined} loading={overview.isLoading} />
        <Metric icon={Trophy} label="Won" value={o?.won_leads ?? 0}
          hint={o ? `${pct(o.win_rate)} win rate` : undefined} loading={overview.isLoading} />
        <Metric icon={Megaphone} label="Active campaigns" value={o?.active_campaigns ?? 0} loading={overview.isLoading} />
        <Metric icon={TrendingUp} label="Open rate" value={outreach.data ? pct(outreach.data.open_rate) : "—"} loading={outreach.isLoading} />
        <Metric icon={AlertTriangle} label="Overdue tasks" value={o?.overdue_tasks ?? 0} loading={overview.isLoading} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Lead funnel</CardTitle>
            <CardDescription>How far leads progress through the lifecycle</CardDescription></CardHeader>
          <CardContent className="space-y-2">
            {funnel.isLoading && <Skeleton className="h-40 w-full" />}
            {funnel.data?.stages.map((s) => (
              <div key={s.status}>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{s.label}</span>
                  <span className="text-muted-foreground">{s.count} · {pct(s.conversion_from_top)}</span>
                </div>
                <div className="h-2 rounded-full bg-accent">
                  <div className="h-2 rounded-full bg-primary"
                    style={{ width: `${topFunnel ? (s.count / topFunnel) * 100 : 0}%` }} />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Activity</CardTitle>
            <CardDescription>Daily sends, replies and new leads</CardDescription></CardHeader>
          <CardContent>
            {ts.isLoading ? <Skeleton className="h-36 w-full" /> : <Sparkline points={ts.data?.points ?? []} />}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader><CardTitle>Outreach by channel</CardTitle>
          <CardDescription>Last {days} days</CardDescription></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="pb-2">Channel</th><th className="pb-2">Sent</th><th className="pb-2">Opened</th>
                <th className="pb-2">Replied</th><th className="pb-2">Bounced</th>
                <th className="pb-2">Open rate</th><th className="pb-2">Reply rate</th>
              </tr>
            </thead>
            <tbody>
              {(outreach.data?.by_channel ?? []).map((c) => (
                <tr key={c.channel} className="border-t">
                  <td className="py-2 capitalize">{c.channel}</td>
                  <td>{c.sent}</td><td>{c.opened}</td><td>{c.replied}</td><td>{c.bounced}</td>
                  <td>{pct(c.open_rate)}</td><td>{pct(c.reply_rate)}</td>
                </tr>
              ))}
              {!outreach.isLoading && (outreach.data?.by_channel.length ?? 0) === 0 && (
                <tr><td colSpan={7} className="py-6 text-center text-muted-foreground">No outreach in this window.</td></tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader><CardTitle>Campaign performance</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="pb-2">Campaign</th><th className="pb-2">State</th><th className="pb-2">Leads</th>
                <th className="pb-2">Sent</th><th className="pb-2">Replied</th>
                <th className="pb-2">Reply rate</th><th className="pb-2">Bounce rate</th>
              </tr>
            </thead>
            <tbody>
              {(campaigns.data?.campaigns ?? []).map((c) => (
                <tr key={c.id} className="border-t">
                  <td className="py-2">{c.name}</td>
                  <td><Badge variant="outline" className="capitalize">{c.state}</Badge></td>
                  <td>{c.total_leads}</td><td>{c.messages_sent}</td><td>{c.replied}</td>
                  <td>{pct(c.reply_rate)}</td><td>{pct(c.bounce_rate)}</td>
                </tr>
              ))}
              {!campaigns.isLoading && (campaigns.data?.campaigns.length ?? 0) === 0 && (
                <tr><td colSpan={7} className="py-6 text-center text-muted-foreground">No campaigns yet.</td></tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" /> AI insights
            </CardTitle>
            <CardDescription>Gemma reads your aggregate numbers and flags what to act on</CardDescription>
          </div>
          <Button onClick={runInsight} disabled={insightBusy}>
            {insightBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Generate
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {!insight && <p className="text-sm text-muted-foreground">Click Generate to analyze the last {days} days.</p>}
          {insight && insight.status !== "ok" && (
            <p className="text-sm text-muted-foreground">
              AI is unavailable or unsure right now. {insight.error ?? ""}
            </p>
          )}
          {insight && insight.status === "ok" && (
            <>
              {typeof insight.output.summary === "string" && (
                <p className="text-sm">{insight.output.summary}</p>
              )}
              <InsightList title="Strengths" items={insight.output.strengths} icon={CheckCircle2} tone="text-emerald-600" />
              <InsightList title="Issues" items={insight.output.issues} icon={AlertTriangle} tone="text-amber-600" />
              <InsightList title="Recommendations" items={insight.output.recommendations} icon={Lightbulb} tone="text-primary" />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
