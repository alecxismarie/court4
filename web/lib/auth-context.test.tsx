import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/lib/auth-context";
import { isPlayerOnboardingPending } from "@/lib/profile-onboarding";

const registerRequest = vi.hoisted(() => vi.fn());
const restoreSession = vi.hoisted(() => vi.fn());
const verifyEmailRequest = vi.hoisted(() => vi.fn());
const completeOnboardingRequest = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/auth", () => ({
  login: vi.fn(),
  logout: vi.fn(),
  register: registerRequest,
  restoreSession,
  verifyEmail: verifyEmailRequest,
  completeOnboarding: completeOnboardingRequest,
}));

vi.mock("@/lib/api/client", () => ({
  AUTH_SESSION_INVALID_EVENT: "court4:auth-session-invalid",
  EMAIL_VERIFICATION_REQUIRED_EVENT: "court4:email-verification-required",
  isDefinitiveAuthenticationFailure: (error: unknown) =>
    typeof error === "object" && error !== null && "status" in error && error.status === 401,
  setAccessToken: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

const newUser = {
  id: "56ae6283-69ee-44b6-9f19-6bf9dc1d7092",
  email: "new@example.com",
  account_status: "active",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  last_login_at: null,
  email_verified_at: null,
  password_changed_at: null,
  display_name: null,
  verification_delivery_mode: "development" as const,
};

describe("auth context registration", () => {
  beforeEach(() => {
    window.localStorage.clear();
    restoreSession.mockReset().mockRejectedValue(new Error("No session"));
    registerRequest.mockReset().mockResolvedValue({ user: newUser });
    verifyEmailRequest.mockReset().mockResolvedValue({
      user: { ...newUser, email_verified_at: "2026-08-01T00:10:00Z" },
      message: "Your email has been verified.",
    });
    completeOnboardingRequest.mockReset().mockResolvedValue({
      ...newUser,
      email_verified_at: "2026-08-01T00:10:00Z",
      display_name: "Alexis",
    });
  });

  it("accepts verification session state and persists completed onboarding", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <VerificationProbe />
      </AuthProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Verify test player" }));
    expect(await screen.findByText("Verified new@example.com")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Complete onboarding" }));
    expect(await screen.findByText("Verified Alexis")).toBeInTheDocument();
  });

  it("marks a newly registered account for one-time player onboarding", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <RegistrationProbe />
      </AuthProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Register test player" }));

    await waitFor(() => {
      expect(registerRequest).toHaveBeenCalledWith(
        "new@example.com",
        "a long secure password",
      );
      expect(isPlayerOnboardingPending(newUser.id)).toBe(true);
    });
  });

  it("clears the complete displayed session and stale onboarding on invalidation", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <RegistrationProbe />
      </AuthProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Register test player" }));
    expect(await screen.findByText("new@example.com")).toBeInTheDocument();
    expect(isPlayerOnboardingPending(newUser.id)).toBe(true);

    act(() => window.dispatchEvent(new Event("court4:auth-session-invalid")));

    await waitFor(() => expect(screen.getByText("Signed out")).toBeInTheDocument());
    expect(screen.queryByText("new@example.com")).not.toBeInTheDocument();
    expect(isPlayerOnboardingPending(newUser.id)).toBe(false);
  });

  it("does not clear a displayed user for a temporary network failure", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <RegistrationProbe />
      </AuthProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Register test player" }));
    expect(await screen.findByText("new@example.com")).toBeInTheDocument();
    restoreSession.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await user.click(screen.getByRole("button", { name: "Refresh test player" }));

    expect(await screen.findByText("refresh failed")).toBeInTheDocument();
    expect(screen.getByText("new@example.com")).toBeInTheDocument();
  });
});

function RegistrationProbe() {
  const auth = useAuth();
  const [result, setResult] = useState("");
  return (
    <div>
      <p>{auth.user?.email ?? "Signed out"}</p>
      <p>{result}</p>
      <button
        type="button"
        onClick={() => void auth.register("new@example.com", "a long secure password")}
      >
        Register test player
      </button>
      <button
        type="button"
        onClick={() => void auth.refreshUser().catch(() => setResult("refresh failed"))}
      >
        Refresh test player
      </button>
    </div>
  );
}

function VerificationProbe() {
  const auth = useAuth();
  return (
    <div>
      <p>{auth.user ? `Verified ${auth.user.display_name ?? auth.user.email}` : "Signed out"}</p>
      <button type="button" onClick={() => void auth.verifyEmail("single-use-token")}>
        Verify test player
      </button>
      <button type="button" onClick={() => void auth.completeOnboarding("Alexis")}>
        Complete onboarding
      </button>
    </div>
  );
}
