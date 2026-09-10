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
  const [campaignId, setCampaignId] = React.useState("");
  const [direction, setDirection] = React.useState("inbound");
  const [channel, setChannel] = React.useState("email");
  const [status, setStatus] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  React.useEffect(() => {
    const campaign = new URLSearchParams(window.location.search).get("campaign");
    if (campaign) { setCampaignId(campaign); setDirection("outbound"); }
  }, []);
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: api.listCampaigns });
  const { data, isLoading, error } = useQuery({
    queryKey: ["inbox", campaignId, direction, channel, status, offset],
    queryFn: () => api.inbox({ direction, offset: String(offset), limit: "50",
      ...(campaignId ? { campaign_id: campaignId } : {}), ...(channel ? { channel } : {}),
      ...(status ? { message_status: status } : {}) }),
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
      <PageHeader title="Campaign mail" description="Organize sent mail and replies by campaign, and inspect each message's activity.">
        <Button variant="outline" onClick={poll} disabled={polling}>
          {polling ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Poll now
        </Button>
      </PageHeader>

      <div className="mb-5 flex flex-wrap gap-3">
        <select aria-label="Mailbox campaign" className="max-w-80 rounded-md border bg-background px-3 py-2 text-sm" value={campaignId} onChange={e => { setCampaignId(e.target.value); setOffset(0); }}><option value="">All campaigns</option>{campaigns.data?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <select aria-label="Message direction" className="rounded-md border bg-background px-3 py-2 text-sm" value={direction} onChange={e => { setDirection(e.target.value); setStatus(""); setOffset(0); }}><option value="inbound">Replies / inbound</option><option value="outbound">Sent / outbound</option></select>
        <select aria-label="Message channel" className="rounded-md border bg-background px-3 py-2 text-sm" value={channel} onChange={e => { setChannel(e.target.value); setOffset(0); }}><option value="email">Email</option><option value="">All channels</option><option value="whatsapp">WhatsApp</option><option value="linkedin">LinkedIn</option></select>
        <select aria-label="Message status" className="rounded-md border bg-background px-3 py-2 text-sm" value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }}><option value="">All statuses</option>{["sent", "delivered", "opened", "replied", "bounced", "failed", "queued", "simulated"].map(s => <option key={s} value={s}>{s}</option>)}</select>
      </div>
      {error && <p role="alert" className="mb-4 text-sm text-destructive">Could not load mail: {error.message}</p>}

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent">
              <InboxIcon className="h-6 w-6 text-accent-foreground" />
            </div>
            <p className="max-w-md text-sm text-muted-foreground">
              No messages match these filters. Choose a campaign and switch between outbound mail and replies.
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
                    {m.lead_name || (m.direction === "outbound" ? m.to_address : m.from_address) || "Unknown contact"}
                  </span>
                  {m.from_address && m.lead_name && (
                    <span className="text-xs text-muted-foreground">{m.from_address}</span>
                  )}
                  <span className="ml-auto text-xs text-muted-foreground">{formatDate(m.created_at)}</span>
                </div>
                <div className="mt-0.5 truncate text-sm">{m.subject || "(no subject)"}</div>
                <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground"><span className="capitalize">{m.channel} · {m.status}</span>{m.campaign_id ? <Link href={`/campaigns/${m.campaign_id}`} className="text-primary hover:underline">{m.campaign_name || "Campaign"}</Link> : <span>Unassigned</span>}</div>
                <details className="mt-2 text-sm"><summary className="cursor-pointer text-primary">Read message & activity</summary><p className="mt-2 whitespace-pre-wrap break-words text-muted-foreground">{m.body || "(empty message)"}</p>
                  <ol className="mt-3 space-y-1 border-l pl-3 text-xs text-muted-foreground">{m.events.map((event, i) => <li key={i}>{formatDate(event.created_at)} · {event.type} ({event.provenance}){event.error ? ` — ${event.error}` : ""}</li>)}</ol>
                </details>
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
      <div className="mt-4 flex items-center justify-between"><Button variant="outline" disabled={offset === 0 || isLoading} onClick={() => setOffset(o => Math.max(0, o - 50))}>Previous</Button><span className="text-xs text-muted-foreground">Page {offset / 50 + 1} · {items.length} messages</span><Button variant="outline" disabled={items.length < 50 || isLoading} onClick={() => setOffset(o => o + 50)}>Next</Button></div>
    </div>
  );
}
