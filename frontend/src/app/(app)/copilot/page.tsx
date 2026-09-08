"use client";
import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Sparkles, Search, Send, Loader2, AlertTriangle, User2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { api, ApiError } from "@/lib/api";
import type { AIResult, Lead, LeadFilter } from "@/lib/types";

interface ChatTurn {
  role: "user" | "assistant";
  text: string;
  status?: AIResult["status"];
}

function DisabledBanner() {
  return (
    <Card className="mb-4 border-warning/40 bg-warning/5">
      <CardContent className="flex items-start gap-3 py-4">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning" />
        <div className="text-sm">
          <p className="font-medium">AI is not configured</p>
          <p className="text-muted-foreground">
            Set <code className="rounded bg-muted px-1 py-0.5 text-xs">GEMINI_API_KEY</code> in the
            backend environment to enable the Copilot. Requests will return{" "}
            <span className="font-medium">unknown</span> until then — the assistant never fabricates
            answers.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function AskTab({ enabled }: { enabled: boolean }) {
  const [turns, setTurns] = React.useState<ChatTurn[]>([]);
  const [q, setQ] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const endRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const ask = async () => {
    const question = q.trim();
    if (!question) return;
    setTurns((t) => [...t, { role: "user", text: question }]);
    setQ("");
    setBusy(true);
    try {
      const res = await api.aiCopilot(question);
      const answer =
        res.status === "ok"
          ? String(res.output.answer ?? "(no answer)")
          : "AI is unavailable or unsure — no answer to give.";
      setTurns((t) => [...t, { role: "assistant", text: answer, status: res.status }]);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Request failed");
      setTurns((t) => [...t, { role: "assistant", text: "Request failed.", status: "error" }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-16rem)] flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto pr-1">
        {turns.length === 0 && (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent">
              <Sparkles className="h-6 w-6 text-accent-foreground" />
            </div>
            <p className="max-w-md text-sm text-muted-foreground">
              Ask about your workspace — lead counts, pipeline status, where to focus. The Copilot
              answers only from your data and says so when it can&apos;t.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {["How many leads have replied?", "What should I focus on next?", "Summarize my pipeline"].map(
                (s) => (
                  <button
                    key={s}
                    onClick={() => setQ(s)}
                    className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-accent"
                  >
                    {s}
                  </button>
                ),
              )}
            </div>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={`flex gap-3 ${t.role === "user" ? "justify-end" : ""}`}>
            {t.role === "assistant" && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
                <Sparkles className="h-4 w-4 text-primary" />
              </div>
            )}
            <div
              className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-3.5 py-2.5 text-sm ${
                t.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"
              }`}
            >
              {t.text}
              {t.status && t.status !== "ok" && (
                <Badge variant="outline" className="ml-2 align-middle text-[10px]">
                  {t.status}
                </Badge>
              )}
            </div>
            {t.role === "user" && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent">
                <User2 className="h-4 w-4" />
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Thinking…
          </div>
        )}
        <div ref={endRef} />
      </div>
      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask();
        }}
      >
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={enabled ? "Ask the Copilot…" : "AI disabled — answers will be 'unknown'"}
          disabled={busy}
        />
        <Button type="submit" disabled={busy || !q.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}

function SearchTab() {
  const [q, setQ] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [leads, setLeads] = React.useState<Lead[] | null>(null);
  const [filter, setFilter] = React.useState<LeadFilter | null>(null);
  const [status, setStatus] = React.useState<AIResult["status"] | null>(null);

  const run = async () => {
    const query = q.trim();
    if (!query) return;
    setBusy(true);
    try {
      const res = await api.aiNlSearch(query);
      setLeads(res.leads.items);
      setFilter(res.filter);
      setStatus(res.result.status);
      if (res.result.status !== "ok") {
        toast.message("AI couldn't translate that — showing unfiltered results.");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder='e.g. "CTOs in Berlin with a score above 70"'
          disabled={busy}
        />
        <Button type="submit" disabled={busy || !q.trim()}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          Search
        </Button>
      </form>

      {filter && filter.conditions && filter.conditions.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Interpreted as:</span>
          {filter.conditions.map((c, i) => (
            <Badge key={i} variant="secondary" className="text-xs">
              {c.field} {c.op} {String(c.value ?? "")}
            </Badge>
          ))}
        </div>
      )}
      {status && status !== "ok" && filter?.conditions?.length === 0 && (
        <p className="mt-3 text-sm text-muted-foreground">
          No filter could be derived from that query.
        </p>
      )}

      {leads && (
        <div className="mt-4 overflow-hidden rounded-lg border">
          <div className="border-b bg-muted/40 px-4 py-2 text-xs font-medium text-muted-foreground">
            {leads.length} match{leads.length === 1 ? "" : "es"}
          </div>
          {leads.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground">
              No leads matched.
            </div>
          ) : (
            <div className="divide-y">
              {leads.map((l) => (
                <div key={l.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                  <span className="font-medium">{l.full_name || "—"}</span>
                  <span className="text-muted-foreground">{l.title || ""}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{l.location || ""}</span>
                  {l.score != null && <Badge variant="outline">{Math.round(l.score)}</Badge>}
                </div>
              ))}
            </div>
          )}
          <div className="border-t px-4 py-2">
            <Link href="/leads" className="text-xs text-primary hover:underline">
              Open Leads →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

export default function CopilotPage() {
  const { data: aiStatus } = useQuery({ queryKey: ["ai-status"], queryFn: () => api.aiStatus() });
  const enabled = aiStatus?.enabled ?? false;

  return (
    <div>
      <PageHeader
        title="AI Copilot"
        description="Ask about your workspace and search leads in plain English"
      >
        {aiStatus && (
          <Badge variant={enabled ? "default" : "outline"}>
            {enabled ? aiStatus.model : "AI disabled"}
          </Badge>
        )}
      </PageHeader>

      {aiStatus && !enabled && <DisabledBanner />}

      <Tabs defaultValue="ask">
        <TabsList>
          <TabsTrigger value="ask">
            <Sparkles className="mr-1.5 h-4 w-4" /> Ask
          </TabsTrigger>
          <TabsTrigger value="search">
            <Search className="mr-1.5 h-4 w-4" /> Lead search
          </TabsTrigger>
        </TabsList>
        <TabsContent value="ask" className="mt-4">
          <AskTab enabled={enabled} />
        </TabsContent>
        <TabsContent value="search" className="mt-4">
          <SearchTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
