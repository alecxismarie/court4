"use client";

import { Eye, EyeOff, LockKeyhole, Mail } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, type KeyboardEvent, useId, useRef, useState } from "react";

import { normalizeApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth-context";

type AuthMode = "login" | "register";

export function LandingAuthPanel() {
  const auth = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const loginTab = useRef<HTMLButtonElement>(null);
  const registerTab = useRef<HTMLButtonElement>(null);
  const descriptionId = useId();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage(null);
    try {
      if (mode === "login") {
        await auth.login(email, password);
        router.replace(safeLandingDestination(searchParams.get("next")));
      } else {
        await auth.register(email, password);
        router.replace("/verification-pending");
      }
    } catch (caught) {
      setMessage(normalizeApiError(caught).message);
    } finally {
      setSubmitting(false);
    }
  }

  function selectMode(nextMode: AuthMode) {
    setMode(nextMode);
    setMessage(null);
  }

  function tabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const nextMode =
      event.key === "ArrowRight" || event.key === "End" ? "register" : "login";
    selectMode(nextMode);
    (nextMode === "login" ? loginTab : registerTab).current?.focus();
  }

  function plannedProvider(provider: "Google" | "Apple") {
    setMessage(`${provider} sign-in is coming soon. Use email and password for now.`);
  }

  return (
    <section className="landing-auth-card" aria-label="Court4 account access">
      <div className="landing-auth-tabs" role="tablist" aria-label="Account access">
        <button
          ref={loginTab}
          type="button"
          role="tab"
          aria-selected={mode === "login"}
          aria-controls="landing-auth-panel"
          tabIndex={mode === "login" ? 0 : -1}
          onClick={() => selectMode("login")}
          onKeyDown={tabKeyDown}
        >
          Log In
        </button>
        <button
          ref={registerTab}
          type="button"
          role="tab"
          aria-selected={mode === "register"}
          aria-controls="landing-auth-panel"
          tabIndex={mode === "register" ? 0 : -1}
          onClick={() => selectMode("register")}
          onKeyDown={tabKeyDown}
        >
          Sign Up
        </button>
      </div>

      <div id="landing-auth-panel" role="tabpanel" className="landing-auth-body">
        <h2>{mode === "login" ? "Welcome back!" : "Create your account"}</h2>
        <p id={descriptionId}>
          {mode === "login"
            ? "Log in to continue your journey."
            : "Start tracking your game with Court4."}
        </p>

        <form onSubmit={submit} aria-describedby={descriptionId}>
          <label htmlFor="landing-email">Email</label>
          <div className="landing-input-wrap">
            <input
              id="landing-email"
              required
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <Mail aria-hidden="true" />
          </div>

          <label htmlFor="landing-password">Password</label>
          <div className="landing-input-wrap">
            <input
              id="landing-password"
              required
              minLength={12}
              maxLength={256}
              type={showPassword ? "text" : "password"}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder={mode === "login" ? "Enter your password" : "At least 12 characters"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <button
              type="button"
              className="landing-password-toggle"
              onClick={() => setShowPassword((visible) => !visible)}
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
            </button>
          </div>

          {mode === "login" ? (
            <div className="landing-auth-options">
              <label
                className="landing-remember"
                title="Court4 currently uses the configured secure session lifetime."
              >
                <input type="checkbox" disabled aria-describedby="remember-policy" />
                Remember Me
              </label>
              <Link href="/forgot-password">Forgot password?</Link>
              <span id="remember-policy" className="sr-only">
                Session duration currently follows Court4 security settings.
              </span>
            </div>
          ) : (
            <p className="landing-password-guidance">
              Use 12 or more characters. Your password is protected with Argon2id.
            </p>
          )}

          {message ? <p className="landing-auth-message" role="status">{message}</p> : null}

          <button type="submit" className="landing-primary-button" disabled={submitting}>
            <LockKeyhole aria-hidden="true" />
            {submitting
              ? "Please wait…"
              : mode === "login"
                ? "Log In"
                : "Create Account"}
          </button>
        </form>

        <div className="landing-auth-divider"><span>Or</span></div>

        <button
          type="button"
          className="landing-social-button"
          onClick={() => plannedProvider("Google")}
          aria-label="Continue with Google, coming soon"
        >
          <span className="landing-google" aria-hidden="true">G</span>
          Continue with Google
          <small>Coming soon</small>
        </button>
        <button
          type="button"
          className="landing-social-button"
          onClick={() => plannedProvider("Apple")}
          aria-label="Continue with Apple, coming soon"
        >
          <span className="landing-apple" aria-hidden="true">●</span>
          Continue with Apple
          <small>Coming soon</small>
        </button>

        <p className="landing-legal" id="legal">
          By continuing, you agree to our<br />
          <a href="#legal">Terms of Service</a> and <a href="#legal">Privacy Policy</a>.
        </p>
      </div>
    </section>
  );
}

export function safeLandingDestination(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/dashboard";
  }
  try {
    const decoded = decodeURIComponent(value);
    if (decoded.startsWith("//") || /^[a-z][a-z0-9+.-]*:/i.test(decoded.slice(1))) {
      return "/dashboard";
    }
  } catch {
    return "/dashboard";
  }
  return value;
}
