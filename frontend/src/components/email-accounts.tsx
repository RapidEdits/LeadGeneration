"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Mail, Plus, Trash2, CheckCircle2, XCircle, Send, RefreshCw, ShieldCheck,
  Inbox as InboxIcon, AlertTriangle, Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { api, ApiError } from "@/lib/api";
import type { ConnectedAccount, DeliverabilityResponse } from "@/lib/types";

const PROVIDER_LABEL: Record<string, string> = { gmail: "Gmail", microsoft: "Microsoft 365", smtp: "SMTP" };

function StatusPill({ status }: { status: ConnectedAccount["status"] }) {
  if (status === "connected")
    return <Badge variant="success" className="gap-1"><CheckCircle2 className="h-3 w-3" /> Connected</Badge>;
  if (status === "error")
    return <Badge variant="destructive" className="gap-1"><XCircle className="h-3 w-3" /> Error</Badge>;
  return <Badge variant="secondary">Disconnected</Badge>;
}

export function EmailAccountsSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["accounts"], queryFn: () => api.listAccounts() });
  const [smtpOpen, setSmtpOpen] = React.useState(false);
  const [oauthBusy, setOauthBusy] = React.useState<string | null>(null);

  const accounts = data ?? [];

  const startOAuth = async (provider: "google" | "microsoft") => {
    setOauthBusy(provider);
    try {
      const { authorize_url } = await api.oauthStart(provider);
      window.location.href = authorize_url;
    } catch (err) {
      toast.error(
        err instanceof ApiError && err.status === 400
          ? `${provider === "google" ? "Google" : "Microsoft"} OAuth isn't configured — set the client ID/secret in the backend .env`
          : "Could not start authorization",
      );
      setOauthBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Email accounts</CardTitle>
          <CardDescription>
            Connect an account to send campaigns and receive replies/bounces. OAuth tokens and SMTP
            credentials are encrypted at rest; sending is gated server-side by can_send().
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => startOAuth("google")} disabled={oauthBusy !== null}>
              {oauthBusy === "google" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
              Connect Gmail
            </Button>
            <Button variant="outline" onClick={() => startOAuth("microsoft")} disabled={oauthBusy !== null}>
              {oauthBusy === "microsoft" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
              Connect Microsoft 365
            </Button>
            <Button onClick={() => setSmtpOpen(true)}><Plus className="h-4 w-4" /> Add SMTP</Button>
          </div>

          <div className="divide-y rounded-lg border">
            {isLoading && <div className="p-4 text-sm text-muted-foreground">Loading…</div>}
            {!isLoading && accounts.length === 0 && (
              <div className="p-6 text-center text-sm text-muted-foreground">
                No email accounts connected yet. Connect one above to start sending.
              </div>
            )}
            {accounts.map((a) => (
              <AccountRow key={a.id} account={a} onChange={() => qc.invalidateQueries({ queryKey: ["accounts"] })} />
            ))}
          </div>
        </CardContent>
      </Card>

      <DeliverabilityCard />

      <SmtpDialog
        open={smtpOpen}
        onOpenChange={setSmtpOpen}
        onConnected={() => {
          setSmtpOpen(false);
          qc.invalidateQueries({ queryKey: ["accounts"] });
        }}
      />
    </div>
  );
}

function AccountRow({ account, onChange }: { account: ConnectedAccount; onChange: () => void }) {
  const [busy, setBusy] = React.useState<string | null>(null);
  const [testOpen, setTestOpen] = React.useState(false);

  const run = async (label: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(label);
    try {
      await fn();
      toast.success(ok);
      onChange();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-accent">
          <Mail className="h-4 w-4 text-accent-foreground" />
        </div>
        <div>
          <div className="flex items-center gap-2 text-sm font-medium">
            {account.from_address || account.external_id}
            <Badge variant="outline">{PROVIDER_LABEL[account.provider] ?? account.provider}</Badge>
          </div>
          <div className="mt-0.5 flex items-center gap-2">
            <StatusPill status={account.status} />
            {account.can_receive && (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <InboxIcon className="h-3 w-3" /> replies & bounces
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <Button size="sm" variant="ghost" onClick={() => setTestOpen(true)}>
          <Send className="h-4 w-4" /> Test
        </Button>
        <Button size="sm" variant="ghost" disabled={busy !== null}
          onClick={() => run("verify", () => api.verifyAccount(account.id), "Verified")}>
          {busy === "verify" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Verify
        </Button>
        <Button size="sm" variant="ghost" className="text-destructive" disabled={busy !== null}
          onClick={() => {
            if (confirm(`Disconnect ${account.from_address}?`))
              run("del", () => api.disconnectAccount(account.id), "Disconnected");
          }}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
      <TestSendDialog account={account} open={testOpen} onOpenChange={setTestOpen} />
    </div>
  );
}

function TestSendDialog({ account, open, onOpenChange }: {
  account: ConnectedAccount; open: boolean; onOpenChange: (v: boolean) => void;
}) {
  const [to, setTo] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const send = async () => {
    setBusy(true);
    try {
      await api.testSend(account.id, to);
      toast.success(`Test email sent to ${to}`);
      onOpenChange(false);
      setTo("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Send failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Send a test email</DialogTitle>
          <DialogDescription>From {account.from_address} via {PROVIDER_LABEL[account.provider]}.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="testto">Recipient</Label>
          <Input id="testto" type="email" value={to} onChange={(e) => setTo(e.target.value)} placeholder="you@example.com" />
        </div>
        <DialogFooter>
          <Button onClick={send} disabled={busy || !to}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Send test
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SmtpDialog({ open, onOpenChange, onConnected }: {
  open: boolean; onOpenChange: (v: boolean) => void; onConnected: () => void;
}) {
  const [form, setForm] = React.useState({
    from_address: "", from_name: "", host: "", port: 587, username: "", password: "",
    imap_host: "", imap_port: 993, imap_username: "", imap_password: "",
  });
  const [busy, setBusy] = React.useState(false);
  const set = (k: string, v: string | number) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setBusy(true);
    try {
      await api.connectSmtp({
        from_address: form.from_address,
        from_name: form.from_name || undefined,
        host: form.host,
        port: Number(form.port),
        username: form.username || undefined,
        password: form.password || undefined,
        imap_host: form.imap_host || undefined,
        imap_port: form.imap_host ? Number(form.imap_port) : undefined,
        imap_username: form.imap_username || undefined,
        imap_password: form.imap_password || undefined,
      });
      toast.success("SMTP account connected");
      onConnected();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not connect");
    } finally {
      setBusy(false);
    }
  };

  const field = (k: keyof typeof form, label: string, type = "text", ph = "") => (
    <div className="space-y-1.5">
      <Label htmlFor={k}>{label}</Label>
      <Input id={k} type={type} value={String(form[k])} placeholder={ph}
        onChange={(e) => set(k, type === "number" ? Number(e.target.value) : e.target.value)} />
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Connect an SMTP account</DialogTitle>
          <DialogDescription>
            We verify the connection before saving. Add IMAP too to detect replies and bounces.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          {field("from_address", "From address", "email", "sales@yourco.com")}
          {field("from_name", "From name", "text", "Your Name")}
          {field("host", "SMTP host", "text", "smtp.yourco.com")}
          {field("port", "SMTP port", "number")}
          {field("username", "SMTP username", "text")}
          {field("password", "SMTP password", "password")}
        </div>
        <div className="mt-2 rounded-lg border bg-muted/40 p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium">
            <InboxIcon className="h-4 w-4" /> IMAP (optional — for replies & bounces)
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {field("imap_host", "IMAP host", "text", "imap.yourco.com")}
            {field("imap_port", "IMAP port", "number")}
            {field("imap_username", "IMAP username", "text")}
            {field("imap_password", "IMAP password", "password")}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={busy || !form.host || !form.from_address}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            Verify & connect
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeliverabilityCard() {
  const [domain, setDomain] = React.useState("");
  const [subject, setSubject] = React.useState("");
  const [body, setBody] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<DeliverabilityResponse | null>(null);

  const check = async () => {
    setBusy(true);
    try {
      setResult(await api.deliverabilityCheck({ domain: domain || undefined, subject: subject || undefined, body: body || undefined }));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Check failed");
    } finally {
      setBusy(false);
    }
  };

  const CheckMark = ({ ok }: { ok: boolean }) =>
    ok ? <CheckCircle2 className="h-4 w-4 text-success" /> : <XCircle className="h-4 w-4 text-destructive" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-5 w-5" /> Deliverability check</CardTitle>
        <CardDescription>Verify sender-domain auth (SPF/DKIM/DMARC) and scan copy for spam signals. Advisory only.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="dom">Sending domain</Label>
            <Input id="dom" value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="yourco.com" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="subj">Subject (optional)</Label>
            <Input id="subj" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Quick question" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bod">Body (optional)</Label>
            <textarea id="bod" value={body} onChange={(e) => setBody(e.target.value)} rows={3}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              placeholder="Paste an email body to score it…" />
          </div>
        </div>
        <Button onClick={check} disabled={busy || (!domain && !subject && !body)}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Run check
        </Button>

        {result?.domain && (
          <div className="rounded-lg border p-4">
            {result.domain.error ? (
              <p className="text-sm text-destructive">{result.domain.error}</p>
            ) : (
              <>
                <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {(["mx", "spf", "dkim", "dmarc"] as const).map((k) => (
                    <div key={k} className="flex items-center gap-2 text-sm">
                      <CheckMark ok={!!result.domain?.checks?.[k]} /> <span className="uppercase">{k}</span>
                    </div>
                  ))}
                </div>
                {result.domain.recommendations && result.domain.recommendations.length > 0 && (
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {result.domain.recommendations.map((r, i) => (
                      <li key={i} className="flex gap-2"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" /> {r}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        )}

        {result?.content && (
          <div className="rounded-lg border p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium">Content score</span>
              <Badge variant={result.content.score >= 76 ? "success" : result.content.score >= 50 ? "warning" : "destructive"}>
                {result.content.score}/100
              </Badge>
            </div>
            {result.content.issues.length === 0 ? (
              <p className="text-sm text-muted-foreground">No content issues detected.</p>
            ) : (
              <ul className="space-y-1 text-sm text-muted-foreground">
                {result.content.issues.map((r, i) => (
                  <li key={i} className="flex gap-2"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" /> {r}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
