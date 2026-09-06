"use client";
import * as React from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";

export function AddLeadDialog({ onCreated, trigger }: { onCreated: () => void; trigger: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [form, setForm] = React.useState({ full_name: "", email: "", title: "", linkedin_url: "", location: "" });

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createLead(Object.fromEntries(Object.entries(form).filter(([, v]) => v)) as never);
      toast.success("Lead added");
      setForm({ full_name: "", email: "", title: "", linkedin_url: "", location: "" });
      setOpen(false);
      onCreated();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not add lead");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Add a lead</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="fn">Full name</Label>
            <Input id="fn" value={form.full_name} onChange={set("full_name")} placeholder="Jane Doe" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="em">Email</Label>
              <Input id="em" type="email" value={form.email} onChange={set("email")} placeholder="jane@acme.com" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ti">Title</Label>
              <Input id="ti" value={form.title} onChange={set("title")} placeholder="VP Sales" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="li">LinkedIn URL</Label>
              <Input id="li" value={form.linkedin_url} onChange={set("linkedin_url")} placeholder="linkedin.com/in/…" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lo">Location</Label>
              <Input id="lo" value={form.location} onChange={set("location")} placeholder="San Francisco" />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Adding…" : "Add lead"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
