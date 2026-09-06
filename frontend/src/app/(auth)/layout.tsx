import { Sparkles } from "lucide-react";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-primary p-10 text-primary-foreground lg:flex">
        <div className="flex items-center gap-2 font-semibold">
          <Sparkles className="h-5 w-5" /> LeadGen
        </div>
        <div className="space-y-4">
          <h1 className="text-3xl font-semibold leading-tight">
            Find, qualify and reach the right leads — responsibly.
          </h1>
          <p className="max-w-md text-primary-foreground/80">
            AI-powered discovery and enrichment, multi-channel outreach across email, LinkedIn
            and WhatsApp, with consent and suppression enforced server-side.
          </p>
        </div>
        <div className="text-xs text-primary-foreground/60">
          Guardrails first · Workspace isolation · Audit logging
        </div>
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/10 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-24 right-10 h-56 w-56 rounded-full bg-white/10 blur-2xl" />
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
