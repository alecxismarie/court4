import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/lib/auth-context";
import { isPlayerOnboardingPending } from "@/lib/profile-onboarding";

const registerRequest = vi.hoisted(() => vi.fn());
const restoreSession = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/auth", () => ({
  login: vi.fn(),
  logout: vi.fn(),
  register: registerRequest,
  restoreSession,
}));

vi.mock("@/lib/api/client", () => ({
  setAccessToken: vi.fn(),
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
};

describe("auth context registration", () => {
  beforeEach(() => {
    window.localStorage.clear();
    restoreSession.mockReset().mockRejectedValue(new Error("No session"));
    registerRequest.mockReset().mockResolvedValue({ user: newUser });
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
});

function RegistrationProbe() {
  const auth = useAuth();
  return (
    <button
      type="button"
      onClick={() => void auth.register("new@example.com", "a long secure password")}
    >
      Register test player
    </button>
  );
}
