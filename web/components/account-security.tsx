"use client";

import { KeyRound, Laptop, MailCheck, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import {
  changePassword,
  type AuthSession,
  listSessions,
  revokeAllSessions,
  revokeSession,
} from "@/lib/api/auth";
import { normalizeApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth-context";
import { formatDateTime } from "@/lib/utils";

export function AccountSecurity() {
  const auth = useAuth();
  const [sessions, setSessions] = useState<AuthSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);

  const refreshSessions = useCallback(async () => {
    setLoadingSessions(true);
    setSessionError(null);
    try {
      setSessions(await listSessions());
    } catch (caught) {
      setSessionError(normalizeApiError(caught).message);
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  async function revokeOne(session: AuthSession) {
    setSessionError(null);
    setSessionMessage(null);
    try {
      const currentPreserved = await revokeSession(session.id);
      if (!currentPreserved) {
        await auth.logout();
        return;
      }
      setSessionMessage("Session signed out.");
      await refreshSessions();
    } catch (caught) {
      setSessionError(normalizeApiError(caught).message);
    }
  }

  async function revokeOthers() {
    setSessionError(null);
    setSessionMessage(null);
    try {
      const count = await revokeAllSessions(true);
      setSessionMessage(
        count === 1 ? "One other session was signed out." : `${count} other sessions were signed out.`,
      );
      await refreshSessions();
    } catch (caught) {
      setSessionError(normalizeApiError(caught).message);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <Header icon={MailCheck} title="Email verification" />
        <p className="mt-3 text-sm text-court-muted">
          Signed in as <strong>{auth.user?.email}</strong>
        </p>
        <p className="mt-2 text-sm">
          {auth.user?.email_verified_at
            ? `Verified ${formatDateTime(auth.user.email_verified_at)}`
            : "Verification is required before uploading or re-analyzing a match."}
        </p>
        {!auth.user?.email_verified_at ? (
          <Link
            href="/verification-pending"
            className="mt-4 inline-block font-semibold text-court-green underline"
          >
            Verify email
          </Link>
        ) : null}
      </section>

      <ChangePassword onChanged={async () => {
        await auth.refreshUser();
        await refreshSessions();
      }} />

      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <Header icon={Laptop} title="Active sessions" />
        <p className="mt-2 text-sm text-court-muted">
          Review browsers signed in to this account. Device labels are approximate.
        </p>
        {sessionError ? <p role="alert" className="mt-3 text-sm text-red-700">{sessionError}</p> : null}
        {sessionMessage ? <p role="status" className="mt-3 text-sm text-green-800">{sessionMessage}</p> : null}
        {loadingSessions ? (
          <p className="mt-4 text-sm text-court-muted">Loading sessions…</p>
        ) : (
          <ul className="mt-4 divide-y divide-court-line">
            {sessions.map((session) => (
              <li key={session.id} className="flex flex-wrap items-center justify-between gap-4 py-4">
                <div>
                  <p className="font-semibold text-court-ink">
                    {session.client_label}
                    {session.current ? (
                      <span className="ml-2 rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">
                        Current
                      </span>
                    ) : null}
                  </p>
                  <p className="mt-1 text-xs text-court-muted">
                    Started {formatDateTime(session.created_at)}
                    {session.last_used_at ? ` · Last used ${formatDateTime(session.last_used_at)}` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void revokeOne(session)}
                  className="rounded-md border border-court-line px-3 py-2 text-sm font-semibold text-court-ink hover:bg-court-panel"
                >
                  {session.current ? "Sign out here" : "Sign out"}
                </button>
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          onClick={() => void revokeOthers()}
          disabled={loadingSessions}
          className="mt-4 rounded-md bg-court-navy px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          Sign out all other sessions
        </button>
      </section>
    </div>
  );
}

function ChangePassword({ onChanged }: { onChanged: () => Promise<void> }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    if (newPassword !== confirmation) {
      setError("New passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await changePassword(currentPassword, newPassword);
      await onChanged();
      setCurrentPassword("");
      setNewPassword("");
      setConfirmation("");
      setMessage("Password changed. Other sessions were signed out.");
    } catch (caught) {
      setError(normalizeApiError(caught).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <Header icon={KeyRound} title="Change password" />
      <form onSubmit={submit} className="mt-4 grid gap-4 sm:max-w-xl">
        <PasswordField
          label="Current password"
          value={currentPassword}
          onChange={setCurrentPassword}
          autoComplete="current-password"
        />
        <PasswordField
          label="New password"
          value={newPassword}
          onChange={setNewPassword}
          autoComplete="new-password"
          minLength={12}
        />
        <PasswordField
          label="Confirm new password"
          value={confirmation}
          onChange={setConfirmation}
          autoComplete="new-password"
          minLength={12}
        />
        {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
        {message ? <p role="status" className="text-sm text-green-800">{message}</p> : null}
        <button
          type="submit"
          disabled={submitting}
          className="w-fit rounded-md bg-court-navy px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          {submitting ? "Changing…" : "Change password"}
        </button>
      </form>
    </section>
  );
}

function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  minLength,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  minLength?: number;
}) {
  return (
    <label className="text-sm font-medium">
      {label}
      <input
        required
        type="password"
        minLength={minLength}
        maxLength={256}
        autoComplete={autoComplete}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-md border border-court-line px-3 py-2"
      />
    </label>
  );
}

function Header({
  icon: Icon,
  title,
}: {
  icon: typeof ShieldCheck;
  title: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="grid h-10 w-10 place-items-center rounded-md bg-court-panel text-court-green">
        <Icon aria-hidden="true" className="h-5 w-5" />
      </span>
      <h2 className="text-lg font-semibold text-court-ink">{title}</h2>
    </div>
  );
}
