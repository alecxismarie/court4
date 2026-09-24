"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect } from "react";

import { useAuth } from "@/lib/auth-context";
import { landingAuthHref } from "@/lib/auth-redirect";
import { AuthForm } from "@/components/auth-form";

const PUBLIC_PATHS = new Set([
  "/",
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
  "/privacy",
  "/terms",
]);
const VERIFICATION_PENDING_PATH = "/verification-pending";

export function AuthGate({ children }: { children: ReactNode }) {
  const { loading, user } = useAuth();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const isPublic = PUBLIC_PATHS.has(pathname);
  const isVerificationPending = pathname === VERIFICATION_PENDING_PATH;
  const isVerified = Boolean(user?.email_verified_at);

  useEffect(() => {
    if (loading || isPublic) return;
    if (!user) {
      if (pathname === "/upload-match") return;
      if (isVerificationPending) {
        router.replace("/");
        return;
      }
      const query = searchParams.toString();
      const intended = `${pathname}${query ? `?${query}` : ""}`;
      router.replace(landingAuthHref("login", intended));
      return;
    }
    if (!isVerified && !isVerificationPending) {
      router.replace(VERIFICATION_PENDING_PATH);
      return;
    }
    if (isVerified && isVerificationPending) {
      router.replace("/dashboard");
    }
  }, [isPublic, isVerificationPending, isVerified, loading, pathname, router, searchParams, user]);

  if (isPublic) return children;
  if (!loading && !user && pathname === "/upload-match") {
    return <section>
      <div className="mx-auto max-w-xl p-6" role="status">
        <h1 className="text-2xl font-semibold">Sign in again to continue</h1>
        <p>Any uploaded parts are preserved until the upload expires. After signing in, you can recover your upload or cancel it.</p>
      </div>
      <AuthForm mode="login" returnTo="/upload-match" />
    </section>;
  }
  if (
    loading ||
    !user ||
    (!isVerified && !isVerificationPending) ||
    (isVerified && isVerificationPending)
  ) {
    return <main className="grid min-h-screen place-items-center text-court-muted">Loading&hellip;</main>;
  }
  return children;
}
