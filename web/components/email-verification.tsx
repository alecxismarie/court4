"use client";

import { Check, LockKeyhole } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { resendVerification } from "@/lib/api/auth";
import { normalizeApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth-context";

export function VerificationPending() {
  const auth = useAuth();
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    if (auth.user?.email_verified_at) router.replace("/dashboard");
  }, [auth.user?.email_verified_at, router]);

  async function resend() {
    setSending(true);
    setMessage(null);
    setError(null);
    try {
      const result = await resendVerification();
      setMessage(result.message);
      if (result.verified) {
        const user = await auth.refreshUser();
        if (user.email_verified_at) router.replace("/dashboard");
      }
    } catch (caught) {
      setError(normalizeApiError(caught).message);
    } finally {
      setSending(false);
    }
  }

  async function checkVerification() {
    setChecking(true);
    setMessage(null);
    setError(null);
    try {
      const user = await auth.refreshUser();
      if (user.email_verified_at) {
        router.replace("/dashboard");
        return;
      }
      setError(
        "We haven’t confirmed your email yet. Open the latest verification link, then check again.",
      );
    } catch (caught) {
      setError(normalizeApiError(caught).message);
    } finally {
      setChecking(false);
    }
  }

  async function leavePending(destination: "/" | "/?auth=signup") {
    setError(null);
    try {
      await auth.logout();
      router.replace(destination);
    } catch (caught) {
      setError(normalizeApiError(caught).message);
    }
  }

  return (
    <Panel title="Verify your email">
      <p className="mt-3 text-base leading-7 text-slate-300">
        Your Court4 account has been created. Verify your email to continue.
      </p>
      <div className="mt-5 min-w-0 rounded-xl border border-white/10 bg-white/5 p-4">
        {auth.user?.verification_delivery_mode === "development" ? (
          <>
            <p className="text-sm text-slate-300">
              Your verification message was captured in the local development inbox.
            </p>
            <p className="mt-1 break-all font-semibold text-white">{auth.user.email}</p>
          </>
        ) : auth.user?.verification_delivery_mode === "external" ? (
          <p className="text-sm text-slate-300">
            We sent a verification link to{" "}
            <span className="break-all font-semibold text-white">{auth.user.email}</span>.
          </p>
        ) : (
          <p className="text-sm text-slate-300">
            Open the latest verification link for{" "}
            <span className="break-all font-semibold text-white">{auth.user?.email}</span>.
          </p>
        )}
      </div>

      <ul className="mt-6 space-y-3 text-sm text-slate-200" aria-label="Why verification matters">
        <TrustItem>Your match videos remain private.</TrustItem>
        <TrustItem>Your progress is saved securely.</TrustItem>
        <TrustItem>Verification protects your Court4 account.</TrustItem>
      </ul>

      {message ? <p role="status" className="mt-5 text-sm text-lime-300">{message}</p> : null}
      {error ? <p role="alert" className="mt-5 text-sm leading-6 text-red-300">{error}</p> : null}
      <button
        type="button"
        disabled={sending}
        onClick={() => void resend()}
        className="mt-6 w-full rounded-lg bg-court-lime px-4 py-3 font-bold text-court-navy transition hover:brightness-105 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-court-navy disabled:opacity-60"
      >
        {sending ? "Sending…" : "Resend verification email"}
      </button>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          type="button"
          disabled={checking}
          onClick={() => void checkVerification()}
          className="rounded-lg border border-white/20 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-court-lime disabled:opacity-60 sm:col-span-2"
        >
          {checking ? "Checking…" : "Check verification status"}
        </button>
        <button
          type="button"
          onClick={() => void leavePending("/?auth=signup")}
          className="rounded-lg px-3 py-2 text-sm font-semibold text-slate-300 underline-offset-4 hover:text-white hover:underline focus:outline-none focus:ring-2 focus:ring-court-lime"
        >
          Use a different email
        </button>
        <button
          type="button"
          onClick={() => void leavePending("/")}
          className="rounded-lg px-3 py-2 text-sm font-semibold text-slate-300 underline-offset-4 hover:text-white hover:underline focus:outline-none focus:ring-2 focus:ring-court-lime"
        >
          Log out
        </button>
      </div>
    </Panel>
  );
}

export function VerifyEmail({ token }: { token: string }) {
  const auth = useAuth();
  const router = useRouter();
  const started = useRef(false);
  const [state, setState] = useState<"working" | "success" | "error">(
    token ? "working" : "error",
  );
  const [message, setMessage] = useState(
    token ? "Verifying your email…" : "This verification link is incomplete.",
  );
  const [errorCode, setErrorCode] = useState<string | null>(
    token ? null : "incomplete_token",
  );
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token || auth.loading || started.current) return;
    started.current = true;
    auth.verifyEmail(token)
      .then((resultMessage) => {
        setState("success");
        setMessage(resultMessage);
        window.history.replaceState(null, "", "/verify-email");
        router.replace("/dashboard");
      })
      .catch((caught) => {
        const caughtError = normalizeApiError(caught);
        setState("error");
        setErrorCode(caughtError.code);
        setMessage(caughtError.message);
      });
  }, [attempt, auth, router, token]);

  async function logoutAndRetry() {
    await auth.logout();
    started.current = false;
    setState("working");
    setErrorCode(null);
    setMessage("Verifying your email…");
    setAttempt((current) => current + 1);
  }

  return (
    <Panel title={state === "success" ? "Email verified" : "Verify your email"}>
      <p
        role={state === "error" ? "alert" : "status"}
        className={`mt-4 text-sm ${state === "error" ? "text-red-300" : "text-slate-300"}`}
      >
        {message}
      </p>
      {state === "error" && errorCode === "verification_account_mismatch" ? (
        <button
          type="button"
          onClick={() => void logoutAndRetry()}
          className="mt-6 rounded-lg bg-court-lime px-4 py-3 font-bold text-court-navy"
        >
          Log out and verify this account
        </button>
      ) : null}
      {state === "error" && errorCode === "token_expired" && auth.user ? (
        <Link href="/verification-pending" className="mt-6 inline-block font-semibold text-court-lime underline">
          Request another link
        </Link>
      ) : null}
      {state === "error" &&
      errorCode !== "verification_account_mismatch" &&
      !(errorCode === "token_expired" && auth.user) ? (
        <Link
          href={
            errorCode === "token_expired"
              ? "/?auth=login&next=%2Fverification-pending"
              : "/?auth=login"
          }
          className="mt-6 inline-block font-semibold text-court-lime underline"
        >
          {errorCode === "token_expired" ? "Log in to request another link" : "Continue to Log In"}
        </Link>
      ) : null}
    </Panel>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main className="min-h-screen overflow-x-hidden bg-court-navy px-4 py-8 text-white sm:py-12">
      <div className="mx-auto flex w-full max-w-xl justify-center">
        <Link href="/" aria-label="Court4 home" className="rounded-lg focus:outline-none focus:ring-2 focus:ring-court-lime">
          <Image
            src="/brand/court4-logo-64.png"
            alt=""
            width={64}
            height={64}
            className="h-14 w-14 rounded-xl"
            priority
          />
        </Link>
      </div>
      <section className="mx-auto mt-6 w-full max-w-xl rounded-2xl border border-white/10 bg-[#102b3f] p-6 shadow-2xl sm:p-10">
        <div className="grid h-12 w-12 place-items-center rounded-xl bg-court-lime/15 text-court-lime">
          <LockKeyhole aria-hidden="true" className="h-6 w-6" />
        </div>
        <p className="mt-6 text-xs font-bold uppercase tracking-[0.22em] text-court-lime">
          ACCOUNT ACTIVATION
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-white sm:text-4xl">{title}</h1>
        {children}
      </section>
    </main>
  );
}

function TrustItem({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-court-lime/15 text-court-lime">
        <Check aria-hidden="true" className="h-3.5 w-3.5" />
      </span>
      <span>{children}</span>
    </li>
  );
}
