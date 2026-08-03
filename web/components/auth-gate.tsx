"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect } from "react";

import { useAuth } from "@/lib/auth-context";

const PUBLIC_PATHS = new Set([
  "/",
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/verification-pending",
  "/verify-email",
]);

export function AuthGate({ children }: { children: ReactNode }) {
  const { loading, user } = useAuth();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const isPublic = PUBLIC_PATHS.has(pathname);

  useEffect(() => {
    if (!loading && !user && !isPublic) {
      const query = searchParams.toString();
      const intended = `${pathname}${query ? `?${query}` : ""}`;
      router.replace(`/login?next=${encodeURIComponent(intended)}`);
    }
  }, [isPublic, loading, pathname, router, searchParams, user]);

  if (isPublic) return children;
  if (loading || !user) {
    return <main className="grid min-h-screen place-items-center text-court-muted">Loading&hellip;</main>;
  }
  return children;
}
