"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

import { useAuth } from "@/lib/auth-context";
import { safeLandingDestination } from "@/lib/auth-redirect";

export function LandingSessionBoundary({ children }: { children: ReactNode }) {
  const [hydrated, setHydrated] = useState(false);
  const { loading, user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated && !loading && user) {
      router.replace(
        user.email_verified_at
          ? safeLandingDestination(searchParams.get("next"))
          : "/verification-pending",
      );
    }
  }, [hydrated, loading, router, searchParams, user]);

  if (!hydrated || loading || user) {
    return (
      <main className="landing-session-loading" aria-live="polite">
        <span className="landing-session-mark" aria-hidden="true">4</span>
        <span>
          {!hydrated || loading ? "Loading Court4…" : "Opening your dashboard…"}
        </span>
      </main>
    );
  }

  return children;
}
