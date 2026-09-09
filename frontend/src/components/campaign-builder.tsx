"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { Plus, Trash2, Mail, Linkedin, MessageCircle, FlaskConical, Sparkles } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { api, ApiError } from "@/lib/api";
import type { Campaign, Channel, ChannelConfig, CampaignStep } from "@/lib/types";

const CHANNELS: { id: Channel; label: string; icon: React.ElementType; phase: string }[] = [
  { id: "email", label: "Email", icon: Mail, phase: "sends in Phase 3" },
  { id: "linkedin", label: "LinkedIn", icon: Linkedin, phase: "assisted send" },
  { id: "whatsapp", label: "WhatsApp", icon: MessageCircle, phase: "OpenWA send" },
];

const DEFAULT_CHANNELS: Record<string, ChannelConfig> = { email: { enabled: true, daily_limit: 50 } };
const DEFAULT_STEPS: CampaignStep[] = [
  { channel: "email", delay_days: 0, subject: "", body_template: "", enabled: true },
];

export function CampaignBuilder({
  trigger,
  campaign,
  onSaved,
  open: openProp,
  onOpenChange,
}: {
  trigger: React.ReactNode;
  /** When set, the dialog edits this campaign instead of creating a new one. */
  campaign?: Campaign;
  /** Called after a successful edit save (edit mode only). */
  onSaved?: () => void;
  /** Optional controlled open state; when provided the parent owns open/close. */
  open?: boolean;
  onOpenChange?: (v: boolean) => void;
}) {
  const router = useRouter();
  const isEdit = !!campaign;
  const controlled = openProp !== undefined;
  const [openState, setOpenState] = React.useState(false);
  const open = controlled ? openProp : openState;
  const setOpen = (v: boolean) => { onOpenChange?.(v); if (!controlled) setOpenState(v); };
  const [busy, setBusy] = React.useState(false);

  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [testMode, setTestMode] = React.useState(true);
  const [channels, setChannels] = React.useState<Record<string, ChannelConfig>>(DEFAULT_CHANNELS);
  const [steps, setSteps] = React.useState<CampaignStep[]>(DEFAULT_STEPS);

  // Load the campaign's current values into the form each time the edit dialog opens.
  const hydrate = React.useCallback(() => {
    if (!campaign) return;
    setName(campaign.name);
    setDescription(campaign.description ?? "");
    setTestMode(campaign.test_mode);
    setChannels(
      Object.keys(campaign.channels).length ? structuredClone(campaign.channels) : DEFAULT_CHANNELS,
    );
    setSteps(
      campaign.steps.length
        ? campaign.steps.map((s) => ({
            channel: s.channel,
            delay_days: s.delay_days,
            subject: s.subject ?? "",
            body_template: s.body_template ?? "",
            ai_prompt: s.ai_prompt ?? "",
            enabled: s.enabled,
          }))
        : structuredClone(DEFAULT_STEPS),
    );
  }, [campaign]);

  const reset = React.useCallback(() => {
    if (isEdit) { hydrate(); return; }
    setName(""); setDescription(""); setTestMode(true);
    setChannels(structuredClone(DEFAULT_CHANNELS));
    setSteps(structuredClone(DEFAULT_STEPS));
  }, [isEdit, hydrate]);

  // Load fresh values whenever the dialog opens (works for both trigger and
  // programmatic opens, e.g. the pause-then-edit flow on active campaigns).
  const prevOpen = React.useRef(false);
  React.useEffect(() => {
    if (open && !prevOpen.current) reset();
    prevOpen.current = open;
  }, [open, reset]);

  const toggleChannel = (id: Channel, enabled: boolean) =>
    setChannels((c) => ({ ...c, [id]: { ...(c[id] ?? {}), enabled } }));
  const setLimit = (id: Channel, v: string) =>
    setChannels((c) => ({ ...c, [id]: { ...(c[id] ?? { enabled: true }), daily_limit: v ? Number(v) : null } }));

  const setStep = (i: number, patch: Partial<CampaignStep>) =>
    setSteps((s) => s.map((st, idx) => (idx === i ? { ...st, ...patch } : st)));
  const addStep = () =>
    setSteps((s) => [...s, { channel: "email", delay_days: 2, subject: "", body_template: "", enabled: true }]);
  const removeStep = (i: number) => setSteps((s) => s.filter((_, idx) => idx !== i));

  const enabledChannels = Object.entries(channels).filter(([, c]) => c.enabled).map(([k]) => k);

  const submit = async () => {
    if (!name.trim()) return toast.error("Give the campaign a name");
    if (enabledChannels.length === 0) return toast.error("Enable at least one channel");
    if (steps.length === 0) return toast.error("Add at least one sequence step");
    if (steps.some((s) => !enabledChannels.includes(s.channel)))
      return toast.error("A step uses a channel that isn't enabled");

    setBusy(true);
    try {
      const body = {
        name, description: description || undefined, test_mode: testMode,
        approval_mode: "auto" as const, channels, steps,
      };
      if (isEdit) {
        await api.updateCampaign(campaign!.id, body);
        toast.success("Campaign updated");
        onSaved?.();
        setOpen(false);
      } else {
        const c = await api.createCampaign(body);
        toast.success("Campaign created");
        setOpen(false);
        reset();
        router.push(`/campaigns/${c.id}`);
      }
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message
          : `Could not ${isEdit ? "update" : "create"} campaign`,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit campaign" : "New campaign"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the channels and message sequence. Changes apply to future sends."
              : "Define the channels and the message sequence. Leads are added on the next screen."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Details */}
          <section className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="cn">Campaign name</Label>
                <Input id="cn" value={name} onChange={(e) => setName(e.target.value)} placeholder="Q3 Founder Outreach" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cd">Description</Label>
                <Input id="cd" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional" />
              </div>
            </div>
            <div className="flex items-center justify-between rounded-lg border bg-accent/40 p-3">
              <div className="flex items-center gap-2 text-sm">
                <FlaskConical className="h-4 w-4 text-primary" />
                <div>
                  <div className="font-medium">Test mode</div>
                  <div className="text-xs text-muted-foreground">
                    Simulates sends — no real messages leave. Recommended until live channels are connected.
                  </div>
                </div>
              </div>
              <Switch checked={testMode} onCheckedChange={setTestMode} />
            </div>
          </section>

          {/* Channels */}
          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Channels</h3>
            <div className="grid gap-2 sm:grid-cols-3">
              {CHANNELS.map((ch) => {
                const cfg = channels[ch.id];
                const on = !!cfg?.enabled;
                return (
                  <div key={ch.id} className="space-y-2 rounded-lg border p-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <ch.icon className="h-4 w-4" /> {ch.label}
                      </div>
                      <Switch checked={on} onCheckedChange={(v) => toggleChannel(ch.id, v)} />
                    </div>
                    {on ? (
                      <div className="space-y-1">
                        <Label className="text-xs text-muted-foreground">Daily limit</Label>
                        <Input
                          type="number" min={1}
                          value={cfg?.daily_limit ?? ""}
                          onChange={(e) => setLimit(ch.id, e.target.value)}
                          className="h-8"
                        />
                      </div>
                    ) : (
                      <p className="text-[11px] text-muted-foreground">{ch.phase}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          {/* Sequence */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Sequence</h3>
              <Button size="sm" variant="outline" onClick={addStep}><Plus className="h-4 w-4" /> Add step</Button>
            </div>
            <div className="space-y-3">
              {steps.map((s, i) => (
                <div key={i} className="rounded-lg border p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <Badge variant="secondary">Step {i + 1}</Badge>
                    {steps.length > 1 && (
                      <Button size="icon" variant="ghost" onClick={() => removeStep(i)} aria-label="Remove step">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-[1fr_140px]">
                    <div className="space-y-1">
                      <Label className="text-xs">Channel</Label>
                      <select
                        value={s.channel}
                        onChange={(e) => setStep(i, { channel: e.target.value as Channel })}
                        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                      >
                        {enabledChannels.length === 0 && <option value="email">email</option>}
                        {enabledChannels.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Wait (days)</Label>
                      <Input type="number" min={0} value={s.delay_days}
                        onChange={(e) => setStep(i, { delay_days: Number(e.target.value) })} className="h-9" />
                    </div>
                  </div>
                  {s.channel === "email" && (
                    <div className="mt-2 space-y-1">
                      <Label className="text-xs">Subject</Label>
                      <Input value={s.subject ?? ""} onChange={(e) => setStep(i, { subject: e.target.value })}
                        placeholder="Quick question, {{first_name}}" />
                    </div>
                  )}
                  <div className="mt-2 space-y-1">
                    <Label className="text-xs">Message</Label>
                    <textarea
                      value={s.body_template ?? ""}
                      onChange={(e) => setStep(i, { body_template: e.target.value })}
                      placeholder="Hi {{first_name}}, …"
                      rows={3}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>
                  <div className="mt-2 space-y-1">
                    <Label className="flex items-center gap-1 text-xs">
                      <Sparkles className="h-3 w-3 text-primary" /> AI personalization (optional)
                    </Label>
                    <textarea
                      value={s.ai_prompt ?? ""}
                      onChange={(e) => setStep(i, { ai_prompt: e.target.value })}
                      placeholder="e.g. Reference the lead's role and industry; keep it under 100 words."
                      rows={2}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                    <p className="text-[11px] text-muted-foreground">
                      When set, Gemma rewrites the message per lead at send time. Falls back to the
                      template above if AI is unavailable.
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Use <code className="rounded bg-muted px-1">{"{{first_name}}"}</code>,{" "}
              <code className="rounded bg-muted px-1">{"{{full_name}}"}</code>,{" "}
              <code className="rounded bg-muted px-1">{"{{title}}"}</code> to personalize.
            </p>
          </section>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? (isEdit ? "Saving…" : "Creating…") : (isEdit ? "Save changes" : "Create campaign")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
