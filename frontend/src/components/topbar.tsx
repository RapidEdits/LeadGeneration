"use client";
import { useRouter } from "next/navigation";
import { LogOut, Building2 } from "lucide-react";
import { CommandPalette } from "./command-palette";
import { ThemeToggle } from "./theme-toggle";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { session } from "@/lib/api";
import { initials } from "@/lib/utils";

export function Topbar() {
  const router = useRouter();
  const profile = typeof window !== "undefined" ? session.profile : null;

  const logout = () => {
    session.clear();
    router.push("/sign-in");
  };

  return (
    <header className="flex h-14 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur">
      <div className="flex-1">
        <CommandPalette />
      </div>
      <div className="hidden items-center gap-1.5 rounded-md border bg-card px-2.5 py-1 text-xs text-muted-foreground sm:flex">
        <Building2 className="h-3.5 w-3.5" />
        {profile?.workspace.name ?? "Workspace"}
      </div>
      <ThemeToggle />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            {initials(profile?.user.full_name || profile?.user.email)}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel>
            <div className="font-medium text-foreground">{profile?.user.full_name || "Account"}</div>
            <div className="truncate text-xs text-muted-foreground">{profile?.user.email}</div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => router.push("/settings")}>Settings</DropdownMenuItem>
          <DropdownMenuItem onSelect={logout} className="text-destructive focus:text-destructive">
            <LogOut className="h-4 w-4" /> Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
