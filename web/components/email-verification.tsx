"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { resendVerification, verifyEmail } from "@/lib/api/auth";
import { normalizeApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth-context";

export function VerificationPending() {
  const auth = useAuth();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  if (auth.user?.email_verified_at) {
    return (
      <Panel title="Email verified">
        <p className="mt-3 text-sm text-court-muted">
          Your account is ready for uploads and re-analysis.
        </p>
        <DashboardLink />
      </Panel>
    );
  }

  async function resend() {
    setSending(true);
    setError(null);
    try {
      const result = await resendVerification();
      setMessage(result.message);
      if (result.verified) await auth.refreshUser();
    } catch (caught) {
      setError(normalizeApiError(caught).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <Panel title="Check your email">
      <p className="mt-3 text-sm leading-6 text-court-muted">
        We sent a verification link to <strong>{auth.user?.email}</strong>. You can
        browse your account now; verify before uploading or analyzing a match.
      </p>
      {message ? <p role="status" className="mt-4 text-sm text-green-800">{message}</p> : null}
      {error ? <p role="alert" className="mt-4 text-sm text-red-700">{error}</p> : null}
      <button
        type="button"
        disabled={sending}
        onClick={() => void resend()}
        className="mt-6 rounded-md bg-court-navy px-4 py-2 font-semibold text-white disabled:opacity-60"
      >
        {sending ? "Sending…" : "Resend verification email"}
      </button>
      <DashboardLink />
    </Panel>
  );
}

export function VerifyEmail({ token }: { token: string }) {
  const auth = useAuth();
  const started = useRef(false);
  const [state, setState] = useState<"working" | "success" | "error">(
    token ? "working" : "error",
  );
  const [message, setMessage] = useState(
    token ? "Verifying your email…" : "This verification link is incomplete.",
  );

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    verifyEmail(token)
      .then(async (result) => {
        setState("success");
        setMessage(result.message);
        try {
          await auth.refreshUser();
        } catch {
          // Verification links also work for signed-out users.
        }
      })
      .catch((caught) => {
        setState("error");
        setMessage(normalizeApiError(caught).message);
      });
  }, [auth, token]);

  return (
    <Panel title={state === "success" ? "Email verified" : "Verify your email"}>
      <p
        role={state === "error" ? "alert" : "status"}
        className={`mt-4 text-sm ${state === "error" ? "text-red-700" : "text-court-muted"}`}
      >
        {message}
      </p>
      {state === "success" ? <DashboardLink /> : null}
      {state === "error" && auth.user ? (
        <Link
          href="/verification-pending"
          className="mt-6 inline-block font-semibold text-court-green underline"
        >
          Request another link
        </Link>
      ) : null}
      {state === "error" && !auth.user ? (
        <Link href="/login" className="mt-6 inline-block font-semibold text-court-green underline">
          Log in
        </Link>
      ) : null}
    </Panel>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main className="grid min-h-[70vh] place-items-center px-4">
      <section className="w-full max-w-lg rounded-xl border border-court-line bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Account verification
        </p>
        <h1 className="mt-2 text-3xl font-bold text-court-ink">{title}</h1>
        {children}
      </section>
    </main>
  );
}

function DashboardLink() {
  return (
    <p className="mt-6">
      <Link href="/dashboard" className="font-semibold text-court-green underline">
        Continue to Court4
      </Link>
    </p>
  );
}
