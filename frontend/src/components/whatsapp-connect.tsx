"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, QrCode, Power, Smartphone } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";

export function WhatsAppConnectSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["whatsapp-session"],
    queryFn: () => api.whatsappSession(),
    // Poll quickly while a QR is pending so "connected" is picked up promptly.
    refetchInterval: (q) => (q.state.data?.status === "qr" ? 2000 : 15000),
  });
  const [busy, setBusy] = React.useState(false);

  const status = data?.status ?? "disconnected";

  const connect = async () => {
    setBusy(true);
    try {
      await api.whatsappConnect();
      qc.invalidateQueries({ queryKey: ["whatsapp-session"] });
      toast.info("Scan the QR code with WhatsApp on your phone");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start session");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm("Disconnect this WhatsApp number?")) return;
    setBusy(true);
    try {
      await api.whatsappDisconnect();
      qc.invalidateQueries({ queryKey: ["whatsapp-session"] });
    } catch {
      toast.error("Could not disconnect");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-warning/40 bg-warning/10 p-4">
        <div className="mb-1 flex items-center gap-2 font-medium">
          <AlertTriangle className="h-4 w-4" /> Unofficial automation — use with care
        </div>
        <p className="text-sm text-muted-foreground">
          WhatsApp connectivity uses an unofficial WhatsApp Web automation library. It violates
          WhatsApp&apos;s Terms of Service and carries a real risk of the connected number being
          banned. This is an accepted, informed choice; the official Cloud API can drop in behind
          the same interface later. Sending is still gated server-side by can_send().
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>WhatsApp session</CardTitle>
          <CardDescription>
            Link a WhatsApp number by scanning a QR code — the same flow as WhatsApp Web. Once
            linked, WhatsApp steps in a live campaign send automatically and replies land in your
            Inbox.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border p-4">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#25d366]/15 text-[#128c7e]">
                <Smartphone className="h-4 w-4" />
              </span>
              <div className="text-sm">
                <div className="font-medium">Session status</div>
                {status === "connected" && data?.me && (
                  <div className="text-xs text-muted-foreground">Number: +{data.me}</div>
                )}
                {data?.mode === "mock" && (
                  <div className="text-xs text-muted-foreground">Mock mode (no real device)</div>
                )}
              </div>
            </div>
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            ) : status === "connected" ? (
              <Badge variant="success" className="gap-1">
                <CheckCircle2 className="h-3 w-3" /> Connected
              </Badge>
            ) : status === "qr" ? (
              <Badge variant="secondary" className="gap-1">
                <QrCode className="h-3 w-3" /> Awaiting scan
              </Badge>
            ) : status === "error" ? (
              <Badge variant="destructive">Error</Badge>
            ) : (
              <Badge variant="secondary">Disconnected</Badge>
            )}
          </div>

          {status === "qr" && data?.qr && (
            <div className="flex flex-col items-center gap-3 rounded-lg border bg-muted/30 p-6">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={data.qr} alt="WhatsApp pairing QR" className="h-52 w-52 rounded bg-white p-2" />
              <p className="text-center text-sm text-muted-foreground">
                Open WhatsApp → <span className="font-medium">Settings → Linked Devices → Link a
                Device</span>, then scan this code.
              </p>
            </div>
          )}

          {status === "error" && data?.error && (
            <p className="text-sm text-destructive">{data.error}</p>
          )}

          <div className="flex gap-2">
            {status === "connected" ? (
              <Button variant="outline" onClick={disconnect} disabled={busy}>
                <Power className="h-4 w-4" /> Disconnect
              </Button>
            ) : (
              <Button onClick={connect} disabled={busy || status === "qr"}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <QrCode className="h-4 w-4" />}
                {status === "qr" ? "Waiting for scan…" : "Connect WhatsApp"}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
