"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";

import { normalizeApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth-context";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const auth = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const isRegister = mode === "register";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await auth[mode](email, password);
      const requested = searchParams.get("next");
      const destination = isRegister
        ? "/verification-pending"
        : requested?.startsWith("/") && !requested.startsWith("//")
          ? requested
          : "/dashboard";
      router.replace(destination);
    } catch (caught) {
      setError(normalizeApiError(caught).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#eef4f0] px-4">
      <form onSubmit={submit} className="w-full max-w-md rounded-xl border border-court-line bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">Court4</p>
        <h1 className="mt-2 text-3xl font-bold text-court-ink">
          {isRegister ? "Create your account" : "Welcome back"}
        </h1>
        <label className="mt-6 block text-sm font-medium">
          Email
          <input
            required
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-2 w-full rounded-md border border-court-line px-3 py-2"
          />
        </label>
        <label className="mt-4 block text-sm font-medium">
          Password
          <input
            required
            minLength={12}
            maxLength={256}
            type="password"
            autoComplete={isRegister ? "new-password" : "current-password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-2 w-full rounded-md border border-court-line px-3 py-2"
          />
        </label>
        {error ? <p role="alert" className="mt-4 text-sm text-red-700">{error}</p> : null}
        <button
          type="submit"
          disabled={submitting}
          className="mt-6 w-full rounded-md bg-court-navy px-4 py-2 font-semibold text-white disabled:opacity-60"
        >
          {submitting ? "Please wait…" : isRegister ? "Create account" : "Log in"}
        </button>
        <p className="mt-5 text-center text-sm text-court-muted">
          {isRegister ? "Already have an account? " : "New to Court4? "}
          <Link className="font-semibold text-court-green underline" href={isRegister ? "/login" : "/register"}>
            {isRegister ? "Log in" : "Register"}
          </Link>
        </p>
        {!isRegister ? (
          <p className="mt-3 text-center text-sm">
            <Link className="font-semibold text-court-green underline" href="/forgot-password">
              Forgot your password?
            </Link>
          </p>
        ) : null}
      </form>
    </main>
  );
}
