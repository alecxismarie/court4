"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";

import { useAuth } from "@/lib/auth-context";

export function LandingSessionBoundary({ children }: { children: ReactNode }) {
  const { loading, user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) {
      router.replace("/dashboard");
    }
  }, [loading, router, user]);

  if (loading || user) {
    return (
      <main className="landing-session-loading" aria-live="polite">
        <span className="landing-session-mark" aria-hidden="true">4</span>
        <span>{loading ? "Loading Court4…" : "Opening your dashboard…"}</span>
      </main>
    );
  }

  return children;
}
