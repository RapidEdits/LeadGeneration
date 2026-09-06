"use client";
import * as React from "react";
import { Upload, ArrowRight, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Step = "upload" | "map" | "done";
type Preview = {
  headers: string[];
  sample_rows: Record<string, string>[];
  total_rows: number;
  importable_fields: string[];
};
type Result = {
  created: number;
  duplicates_skipped: number;
  suppressed_skipped: number;
  errors: string[];
};

const IGNORE = "__ignore__";

// Best-effort auto-map a CSV header to a lead field.
function guess(header: string, fields: string[]): string {
  const h = header.toLowerCase().replace(/[^a-z]/g, "");
  const table: Record<string, string> = {
    email: "email", mail: "email", fullname: "full_name", name: "full_name",
    firstname: "first_name", lastname: "last_name", title: "title", jobtitle: "title",
    phone: "phone", mobile: "phone", linkedin: "linkedin_url", linkedinurl: "linkedin_url",
    location: "location", city: "location", notes: "notes",
  };
  const match = table[h];
  return match && fields.includes(match) ? match : IGNORE;
}

export function ImportWizard({
  open, onOpenChange, onImported,
}: { open: boolean; onOpenChange: (v: boolean) => void; onImported: () => void }) {
  const [step, setStep] = React.useState<Step>("upload");
  const [busy, setBusy] = React.useState(false);
  const [fileName, setFileName] = React.useState("");
  const [preview, setPreview] = React.useState<Preview | null>(null);
  const [map, setMap] = React.useState<Record<string, string>>({});
  const [rows, setRows] = React.useState<Record<string, string>[]>([]);
  const [result, setResult] = React.useState<Result | null>(null);

  const reset = () => {
    setStep("upload"); setPreview(null); setMap({}); setRows([]); setResult(null); setFileName("");
  };

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setBusy(true);
    try {
      // Preview (headers + samples) via multipart, and parse full rows client-side.
      const form = new FormData();
      form.append("file", file);
      const p = await api.previewCsv(form);
      setPreview(p);
      const initial: Record<string, string> = {};
      p.headers.forEach((h) => (initial[h] = guess(h, p.importable_fields)));
      setMap(initial);
      setRows(await parseCsv(file));
      setStep("map");
    } catch {
      toast.error("Could not read that CSV");
    } finally {
      setBusy(false);
    }
  };

  const runImport = async () => {
    const column_map: Record<string, string> = {};
    Object.entries(map).forEach(([col, field]) => {
      if (field && field !== IGNORE) column_map[col] = field;
    });
    if (!Object.values(column_map).includes("email") &&
        !Object.values(column_map).includes("full_name")) {
      toast.error("Map at least an Email or Name column");
      return;
    }
    setBusy(true);
    try {
      const res = await api.importCsv({ column_map, rows, source_name: fileName || "CSV Import" });
      setResult(res);
      setStep("done");
      onImported();
    } catch {
      toast.error("Import failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import leads from CSV</DialogTitle>
          <DialogDescription>
            Rows run through duplicate detection and your suppression list automatically.
          </DialogDescription>
        </DialogHeader>

        {step === "upload" && (
          <label className="flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed py-12 transition-colors hover:bg-accent/40">
            <Upload className="h-8 w-8 text-muted-foreground" />
            <div className="text-center text-sm">
              <span className="font-medium text-primary">Choose a CSV file</span>
              <p className="text-muted-foreground">or drag it here</p>
            </div>
            <input type="file" accept=".csv,text/csv" className="hidden" onChange={onFile} disabled={busy} />
          </label>
        )}

        {step === "map" && preview && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {preview.total_rows} rows found. Map each column to a lead field.
            </p>
            <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
              {preview.headers.map((h) => (
                <div key={h} className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
                  <div className="truncate rounded-md border bg-muted/40 px-3 py-2 text-sm font-medium">{h}</div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  <select
                    value={map[h] ?? IGNORE}
                    onChange={(e) => setMap((m) => ({ ...m, [h]: e.target.value }))}
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                  >
                    <option value={IGNORE}>— Ignore —</option>
                    {preview.importable_fields.map((f) => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>
        )}

        {step === "done" && result && (
          <div className="space-y-4 py-2">
            <div className="flex items-center gap-3 rounded-lg border border-success/30 bg-success/10 p-4">
              <CheckCircle2 className="h-6 w-6 text-success" />
              <div>
                <div className="font-medium">{result.created} leads imported</div>
                <div className="text-sm text-muted-foreground">
                  {result.duplicates_skipped} duplicates and {result.suppressed_skipped} suppressed rows skipped.
                </div>
              </div>
            </div>
            {result.errors.length > 0 && (
              <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
                <div className="mb-1 flex items-center gap-2 font-medium">
                  <AlertTriangle className="h-4 w-4" /> {result.errors.length} row issue(s)
                </div>
                <ul className="ml-6 list-disc text-muted-foreground">
                  {result.errors.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          {step === "map" && (
            <>
              <Button variant="outline" onClick={reset}>Back</Button>
              <Button onClick={runImport} disabled={busy}>{busy ? "Importing…" : "Import leads"}</Button>
            </>
          )}
          {step === "done" && (
            <Button onClick={() => { onOpenChange(false); reset(); }}>Done</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Minimal RFC-4180-ish CSV parser (handles quoted fields + embedded commas/quotes).
async function parseCsv(file: File): Promise<Record<string, string>[]> {
  const text = await file.text();
  const rows: string[][] = [];
  let field = "", row: string[] = [], inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else inQuotes = false;
      } else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      if (field !== "" || row.length) { row.push(field); rows.push(row); }
      field = ""; row = [];
    } else field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  if (!rows.length) return [];
  const headers = rows[0];
  return rows.slice(1).map((r) => {
    const obj: Record<string, string> = {};
    headers.forEach((h, idx) => (obj[h] = (r[idx] ?? "").trim()));
    return obj;
  });
}
