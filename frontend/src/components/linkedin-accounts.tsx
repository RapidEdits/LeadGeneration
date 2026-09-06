"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Linkedin, Plus, Trash2, CheckCircle2, ExternalLink, ArrowRight } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import type { LinkedInAccount } from "@/lib/types";

export function LinkedInAccountsSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["linkedin-accounts"],
    queryFn: () => api.linkedinAccounts(),
  });
  const [name, setName] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const accounts = data ?? [];

  const connect = async () => {
    if (!name.trim()) return toast.error("Enter the sending person's name");
    setBusy(true);
    try {
      await api.connectLinkedin({ display_name: name.trim(), profile_url: url.trim() || null });
      toast.success("LinkedIn identity connected");
      setName("");
      setUrl("");
      qc.invalidateQueries({ queryKey: ["linkedin-accounts"] });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not connect");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (a: LinkedInAccount) => {
    if (!confirm(`Disconnect ${a.display_name}?`)) return;
    try {
      await api.disconnectLinkedin(a.id);
      qc.invalidateQueries({ queryKey: ["linkedin-accounts"] });
    } catch {
      toast.error("Could not disconnect");
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>LinkedIn — assisted workflow</CardTitle>
          <CardDescription>
            LinkedIn cold outreach can&apos;t be automated compliantly, so we never store your
            LinkedIn password or automate your account. Instead, the AI drafts each message and
            the engine queues it as a task; you open the profile, send it yourself, then mark it
            sent. Connecting an identity is what lets a live LinkedIn campaign leave test mode.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="li-name">Sending person</Label>
              <Input
                id="li-name"
                placeholder="e.g. Alex Rivera"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="li-url">Profile URL (optional)</Label>
              <Input
                id="li-url"
                placeholder="https://linkedin.com/in/…"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
          </div>
          <Button onClick={connect} disabled={busy}>
            <Plus className="h-4 w-4" /> Connect identity
          </Button>

          <div className="rounded-md border bg-muted/40 p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">
                Work the queue of drafted messages ready to send.
              </span>
              <Link href="/linkedin">
                <Button variant="outline" size="sm">
                  Open task queue <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </Link>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Connected identities</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : accounts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No LinkedIn identity connected yet.</p>
          ) : (
            <ul className="divide-y">
              {accounts.map((a) => (
                <li key={a.id} className="flex items-center justify-between py-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#0a66c2]/10 text-[#0a66c2]">
                      <Linkedin className="h-4 w-4" />
                    </span>
                    <div>
                      <div className="flex items-center gap-2 font-medium">
                        {a.display_name}
                        <Badge variant="success" className="gap-1">
                          <CheckCircle2 className="h-3 w-3" /> Connected
                        </Badge>
                      </div>
                      {a.profile_url && (
                        <a
                          href={a.profile_url}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-1 text-xs text-muted-foreground hover:underline"
                        >
                          {a.profile_url} <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => remove(a)}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
