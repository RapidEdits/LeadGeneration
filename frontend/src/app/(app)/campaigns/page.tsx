"use client";
import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Megaphone, Plus, Users, Send, FlaskConical, ArrowRight } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { CampaignStateBadge } from "@/components/campaign-state-badge";
import { CampaignBuilder } from "@/components/campaign-builder";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function CampaignsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["campaigns"], queryFn: () => api.listCampaigns() });
  const campaigns = data ?? [];

  return (
    <div>
      <PageHeader title="Campaigns" description="Multi-channel outreach sequences">
        <CampaignBuilder trigger={<Button><Plus className="h-4 w-4" /> New campaign</Button>} />
      </PageHeader>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-36 rounded-xl" />)}
        </div>
      ) : campaigns.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed py-16 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent">
            <Megaphone className="h-6 w-6 text-accent-foreground" />
          </div>
          <div>
            <p className="font-medium">No campaigns yet</p>
            <p className="text-sm text-muted-foreground">
              Build a sequence, add leads, and launch. Test mode simulates sends safely.
            </p>
          </div>
          <CampaignBuilder trigger={<Button><Plus className="h-4 w-4" /> New campaign</Button>} />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {campaigns.map((c) => (
            <Link key={c.id} href={`/campaigns/${c.id}`}>
              <Card className="group h-full transition-shadow hover:shadow-md">
                <CardContent className="space-y-4 p-5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-medium">{c.name}</span>
                        {c.test_mode && (
                          <Badge variant="outline" className="gap-1 text-[10px]">
                            <FlaskConical className="h-3 w-3" /> Test
                          </Badge>
                        )}
                      </div>
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {c.steps.length} step{c.steps.length === 1 ? "" : "s"} ·{" "}
                        {Object.entries(c.channels).filter(([, v]) => v.enabled).map(([k]) => k).join(", ") || "no channels"}
                      </div>
                    </div>
                    <CampaignStateBadge state={c.state} />
                  </div>

                  <div className="flex items-center gap-4 text-sm">
                    <span className="flex items-center gap-1.5 text-muted-foreground">
                      <Users className="h-4 w-4" /> {c.stats?.total ?? 0} leads
                    </span>
                    <span className="flex items-center gap-1.5 text-muted-foreground">
                      <Send className="h-4 w-4" /> {c.stats?.messages_sent ?? 0} sent
                    </span>
                    <span className="ml-auto flex items-center gap-1 text-primary opacity-0 transition-opacity group-hover:opacity-100">
                      Open <ArrowRight className="h-3.5 w-3.5" />
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground">Created {formatDate(c.created_at)}</div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
