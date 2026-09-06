"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { session } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  React.useEffect(() => {
    router.replace(session.token ? "/dashboard" : "/sign-in");
  }, [router]);
  return (
    <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
      Loading…
    </div>
  );
}
