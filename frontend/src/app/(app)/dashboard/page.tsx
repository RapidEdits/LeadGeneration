"use client";
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Users, UserCheck, Send, MessageSquareReply, TrendingUp, Sparkles, CheckCircle2, Clock,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api, session } from "@/lib/api";

function useLeadCount(conditions: { field: string; op: string; value?: unknown }[] = []) {
  return useQuery({
    queryKey: ["lead-count", conditions],
    queryFn: async () => {
      const res = await api.searchLeads({ conditions, page: 1, page_size: 1 });
      return res.total;
    },
  });
}

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

export default function DashboardPage() {
  const profile = typeof window !== "undefined" ? session.profile : null;
  const total = useLeadCount();
  const qualified = useLeadCount([{ field: "status", op: "eq", value: "qualified" }]);
  const contacted = useLeadCount([{ field: "status", op: "eq", value: "contacted" }]);
  const replied = useLeadCount([{ field: "status", op: "eq", value: "replied" }]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const name = profile?.user.full_name?.split(" ")[0] || "there";

  return (
    <div>
      <PageHeader title={`${greeting}, ${name}`} description="Here's what's happening across your workspace." />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric icon={Users} label="Total leads" value={total.data ?? 0} loading={total.isLoading} />
        <Metric icon={UserCheck} label="Qualified" value={qualified.data ?? 0} loading={qualified.isLoading} />
        <Metric icon={Send} label="Contacted" value={contacted.data ?? 0} loading={contacted.isLoading} />
        <Metric icon={MessageSquareReply} label="Replied" value={replied.data ?? 0} loading={replied.isLoading} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Campaign performance</CardTitle>
              <CardDescription>Sends, opens and replies over time</CardDescription>
            </div>
            <Badge variant="outline">Phase 8</Badge>
          </CardHeader>
          <CardContent>
            <div className="flex h-56 flex-col items-center justify-center gap-2 rounded-lg border border-dashed text-center">
              <TrendingUp className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Analytics populate once campaigns are live.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" /> AI recommendations
            </CardTitle>
            <Badge variant="outline">Phase 4</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              "Import your first lead list to get started",
              "Connect a sending account under Settings",
              "AI qualification activates in Phase 4",
            ].map((t) => (
              <div key={t} className="flex items-start gap-2 rounded-lg border bg-card/50 p-3 text-sm">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <span>{t}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Recent replies</CardTitle></CardHeader>
          <CardContent>
            <EmptyRow icon={MessageSquareReply} text="No replies yet — they'll appear here once outreach begins." />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Your tasks</CardTitle></CardHeader>
          <CardContent>
            <EmptyRow icon={Clock} text="No tasks yet. The CRM & tasks land in Phase 7." />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function EmptyRow({ icon: Icon, text }: { icon: React.ElementType; text: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
      <Icon className="h-7 w-7 text-muted-foreground" />
      <p className="text-sm text-muted-foreground">{text}</p>
    </div>
  );
}
