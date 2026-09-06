"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  User, Building2, Sparkles, Mail, Linkedin, MessageCircle, Gauge, ShieldBan, Lock,
  Plus, Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { api, session, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/utils";
import { EmailAccountsSection } from "@/components/email-accounts";
import { LinkedInAccountsSection } from "@/components/linkedin-accounts";
import { WhatsAppConnectSection } from "@/components/whatsapp-connect";

const SECTIONS = [
  { id: "profile", label: "Profile", icon: User },
  { id: "workspace", label: "Workspace", icon: Building2 },
  { id: "ai", label: "AI / Gemini", icon: Sparkles },
  { id: "email", label: "Email Accounts", icon: Mail },
  { id: "linkedin", label: "LinkedIn", icon: Linkedin },
  { id: "whatsapp", label: "WhatsApp", icon: MessageCircle },
  { id: "limits", label: "Sending Limits", icon: Gauge },
  { id: "suppression", label: "Suppression", icon: ShieldBan },
  { id: "security", label: "Security", icon: Lock },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

export default function SettingsPage() {
  const [active, setActive] = React.useState<SectionId>("profile");

  // Surface the result of an OAuth email connect (redirected back with ?email=...).
  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("email");
    if (!status) return;
    setActive("email");
    if (status === "connected") toast.success(`Email account connected${params.get("msg") ? `: ${params.get("msg")}` : ""}`);
    else if (status === "error") toast.error(params.get("msg") || "Could not connect email account");
    window.history.replaceState({}, "", window.location.pathname);
  }, []);

  return (
    <div>
      <PageHeader title="Settings" description="Manage your account, workspace and integrations" />
      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <nav className="flex gap-1 overflow-x-auto lg:flex-col">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              onClick={() => setActive(s.id)}
              className={cn(
                "flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active === s.id ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/60",
              )}
            >
              <s.icon className="h-4 w-4" /> {s.label}
            </button>
          ))}
        </nav>
        <div>
          {active === "profile" && <ProfileSection />}
          {active === "workspace" && <WorkspaceSection />}
          {active === "ai" && <AISection />}
          {active === "email" && <EmailAccountsSection />}
          {active === "linkedin" && <LinkedInAccountsSection />}
          {active === "whatsapp" && <WhatsAppConnectSection />}
          {active === "limits" && <IntegrationStub title="Sending limits" phase="Phase 2" icon={Gauge}
            text="Per-channel daily caps, warm-up ramp, schedule windows and rate budgets. Enforced server-side by the can_send() gate in the worker — never bypassed by the UI." />}
          {active === "suppression" && <SuppressionSection />}
          {active === "security" && <SecuritySection />}
        </div>
      </div>
    </div>
  );
}

function SectionCard({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function ProfileSection() {
  const profile = typeof window !== "undefined" ? session.profile : null;
  return (
    <SectionCard title="Profile" description="Your personal details">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2"><Label>Name</Label><Input defaultValue={profile?.user.full_name ?? ""} readOnly /></div>
        <div className="space-y-2"><Label>Email</Label><Input defaultValue={profile?.user.email ?? ""} readOnly /></div>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">Editable profile fields land alongside account management.</p>
    </SectionCard>
  );
}

function WorkspaceSection() {
  const profile = typeof window !== "undefined" ? session.profile : null;
  return (
    <SectionCard title="Workspace" description="Shared settings for your team">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2"><Label>Workspace name</Label><Input defaultValue={profile?.workspace.name ?? ""} readOnly /></div>
        <div className="space-y-2"><Label>Your role</Label>
          <div><Badge className="capitalize">{profile?.workspace.role}</Badge></div>
        </div>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Every record is isolated to this workspace. Roles: owner, admin, sales, viewer.
      </p>
    </SectionCard>
  );
}

function AISection() {
  const { data, isLoading } = useQuery({ queryKey: ["ai-status"], queryFn: () => api.aiStatus() });
  const enabled = data?.enabled ?? false;
  const model = data?.model ?? "gemma-3-27b-it";
  return (
    <SectionCard title="AI / Gemini" description="The model behind qualification, personalization and the copilot">
      <div className="flex items-center justify-between rounded-lg border p-4">
        <div>
          <div className="font-medium">Gemma 3 27B</div>
          <div className="text-sm text-muted-foreground">{model} · via Google Generative Language API</div>
        </div>
        {isLoading ? (
          <Badge variant="outline">Checking…</Badge>
        ) : enabled ? (
          <Badge variant="success">Connected</Badge>
        ) : (
          <Badge variant="warning">Key not set</Badge>
        )}
      </div>
      <p className="mt-4 text-sm text-muted-foreground">
        {enabled ? (
          <>
            AI is active. It powers lead qualification &amp; scoring, per-lead message personalization,
            reply classification, campaign analysis, natural-language lead search and the Copilot. Every
            output is recorded to an audit trail, and the model returns “unknown” rather than fabricating.
          </>
        ) : (
          <>
            Set <code className="rounded bg-muted px-1">GEMINI_API_KEY</code> in the backend environment to
            enable AI features. The model id is env-driven and swappable. AI returns “unknown” rather than
            fabricating when unsure.
          </>
        )}
      </p>
    </SectionCard>
  );
}

function IntegrationStub({ title, phase, text, icon: Icon }: { title: string; phase: string; text: string; icon: React.ElementType }) {
  return (
    <SectionCard title={title}>
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent">
          <Icon className="h-6 w-6 text-accent-foreground" />
        </div>
        <Badge variant="outline">{phase}</Badge>
        <p className="max-w-md text-sm text-muted-foreground">{text}</p>
      </div>
    </SectionCard>
  );
}

function SecuritySection() {
  return (
    <SectionCard title="Security" description="How your data is protected">
      <ul className="space-y-2 text-sm text-muted-foreground">
        {[
          "Passwords hashed with bcrypt",
          "JWT session tokens; workspace scoping on every request",
          "Connected-account credentials encrypted at rest (Fernet)",
          "RBAC roles: owner / admin / sales / viewer",
          "Audit log records every mutation",
          "Secrets provided via environment only — never hardcoded",
        ].map((t) => (
          <li key={t} className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-success" /> {t}
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

function SuppressionSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["suppression"], queryFn: () => api.listSuppression() });
  const [value, setValue] = React.useState("");
  const [channel, setChannel] = React.useState("all");
  const [busy, setBusy] = React.useState(false);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) return;
    setBusy(true);
    try {
      await api.addSuppression({ channel, value });
      toast.success("Added to suppression list");
      setValue("");
      qc.invalidateQueries({ queryKey: ["suppression"] });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not add");
    } finally {
      setBusy(false);
    }
  };

  const entries = data ?? [];
  return (
    <SectionCard title="Suppression list" description="Global do-not-contact — honored across every campaign and channel">
      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <div className="flex-1 space-y-2 min-w-[200px]">
          <Label htmlFor="sv">Email, phone or URL</Label>
          <Input id="sv" value={value} onChange={(e) => setValue(e.target.value)} placeholder="blocked@example.com" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="sc">Channel</Label>
          <select id="sc" value={channel} onChange={(e) => setChannel(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm">
            <option value="all">All</option>
            <option value="email">Email</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="linkedin">LinkedIn</option>
          </select>
        </div>
        <Button type="submit" disabled={busy}><Plus className="h-4 w-4" /> Add</Button>
      </form>

      <div className="mt-5 divide-y rounded-lg border">
        {isLoading && <div className="p-4 text-sm text-muted-foreground">Loading…</div>}
        {!isLoading && entries.length === 0 && (
          <div className="p-6 text-center text-sm text-muted-foreground">
            No suppressed contacts. Add addresses here or via bulk actions on the Leads page.
          </div>
        )}
        {entries.map((e) => (
          <div key={e.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
            <div className="flex items-center gap-3">
              <ShieldBan className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium">{e.value}</span>
              <Badge variant="outline" className="capitalize">{e.channel}</Badge>
              <span className="text-xs text-muted-foreground capitalize">{e.reason}</span>
            </div>
            <span className="text-xs text-muted-foreground">{formatDate(e.created_at)}</span>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}
