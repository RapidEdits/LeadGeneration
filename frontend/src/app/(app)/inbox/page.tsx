"use client";
import * as React from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Inbox as InboxIcon, Loader2, CornerUpLeft } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function InboxPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["inbox"],
    queryFn: () => api.inbox(),
    refetchInterval: 15000,
  });
  const [polling, setPolling] = React.useState(false);

  const poll = async () => {
    setPolling(true);
    try {
      const { outcomes } = await api.pollInbox();
      const replies = outcomes.reply_recorded ?? 0;
      const bounces = outcomes.bounce_recorded ?? 0;
      toast.success(
        replies || bounces
          ? `Polled: ${replies} repl${replies === 1 ? "y" : "ies"}, ${bounces} bounce${bounces === 1 ? "" : "s"}`
          : "Polled — nothing new",
      );
      qc.invalidateQueries({ queryKey: ["inbox"] });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Poll failed");
    } finally {
      setPolling(false);
    }
  };

  const items = data ?? [];

  return (
    <div>
      <PageHeader title="Inbox" description="Replies and inbound messages across your campaigns">
        <Button variant="outline" onClick={poll} disabled={polling}>
          {polling ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Poll now
        </Button>
      </PageHeader>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent">
              <InboxIcon className="h-6 w-6 text-accent-foreground" />
            </div>
            <p className="max-w-md text-sm text-muted-foreground">
              No replies yet. When a lead responds to a campaign email, it lands here and their
              sequence is paused automatically. Connected accounts are polled every couple of
              minutes — or click <span className="font-medium">Poll now</span>.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="divide-y rounded-lg border">
          {items.map((m) => (
            <div key={m.id} className="flex gap-3 px-4 py-3.5">
              <CornerUpLeft className="mt-0.5 h-4 w-4 shrink-0 text-success" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">
                    {m.lead_name || m.from_address || "Unknown sender"}
                  </span>
                  {m.from_address && m.lead_name && (
                    <span className="text-xs text-muted-foreground">{m.from_address}</span>
                  )}
                  <span className="ml-auto text-xs text-muted-foreground">{formatDate(m.created_at)}</span>
                </div>
                <div className="mt-0.5 truncate text-sm">{m.subject || "(no subject)"}</div>
                {m.body && (
                  <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{m.body}</p>
                )}
                {m.lead_id && (
                  <Link href="/leads" className="mt-1 inline-block text-xs text-primary hover:underline">
                    View lead
                  </Link>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
