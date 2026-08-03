"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import { forgotPassword, resetPassword } from "@/lib/api/auth";
import { normalizeApiError } from "@/lib/api/client";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      setMessage(await forgotPassword(email));
    } catch (caught) {
      setError(normalizeApiError(caught).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthPanel title="Reset your password">
      <form onSubmit={submit}>
        <p className="mt-3 text-sm leading-6 text-court-muted">
          Enter your account email. Court4 will send a time-limited reset link if the
          account is active.
        </p>
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
        <Status message={message} error={error} />
        <button
          type="submit"
          disabled={submitting}
          className="mt-6 w-full rounded-md bg-court-navy px-4 py-2 font-semibold text-white disabled:opacity-60"
        >
          {submitting ? "Sending…" : "Send reset link"}
        </button>
        <BackToLogin />
      </form>
    </AuthPanel>
  );
}

export function ResetPasswordForm({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password !== confirmation) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      setMessage(await resetPassword(token, password));
    } catch (caught) {
      setError(normalizeApiError(caught).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthPanel title="Choose a new password">
      {token ? (
        <form onSubmit={submit}>
          <PasswordInput
            label="New password"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
          />
          <PasswordInput
            label="Confirm new password"
            value={confirmation}
            onChange={setConfirmation}
            autoComplete="new-password"
          />
          <Status message={message} error={error} />
          <button
            type="submit"
            disabled={submitting || Boolean(message)}
            className="mt-6 w-full rounded-md bg-court-navy px-4 py-2 font-semibold text-white disabled:opacity-60"
          >
            {submitting ? "Resetting…" : "Reset password"}
          </button>
        </form>
      ) : (
        <p role="alert" className="mt-4 text-sm text-red-700">
          This reset link is incomplete. Request a new password reset email.
        </p>
      )}
      <BackToLogin />
    </AuthPanel>
  );
}

function AuthPanel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <main className="grid min-h-screen place-items-center bg-[#eef4f0] px-4">
      <section className="w-full max-w-md rounded-xl border border-court-line bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Court4
        </p>
        <h1 className="mt-2 text-3xl font-bold text-court-ink">{title}</h1>
        {children}
      </section>
    </main>
  );
}

function PasswordInput({
  label,
  value,
  onChange,
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
}) {
  return (
    <label className="mt-5 block text-sm font-medium">
      {label}
      <input
        required
        minLength={12}
        maxLength={256}
        type="password"
        autoComplete={autoComplete}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-md border border-court-line px-3 py-2"
      />
    </label>
  );
}

function Status({
  message,
  error,
}: {
  message: string | null;
  error: string | null;
}) {
  if (error) {
    return <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>;
  }
  if (message) {
    return <p role="status" className="mt-4 rounded-md bg-green-50 p-3 text-sm text-green-800">{message}</p>;
  }
  return null;
}

function BackToLogin() {
  return (
    <p className="mt-5 text-center text-sm">
      <Link className="font-semibold text-court-green underline" href="/login">
        Back to login
      </Link>
    </p>
  );
}
