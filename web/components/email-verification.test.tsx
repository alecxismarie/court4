import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VerificationPending, VerifyEmail } from "@/components/email-verification";
import { resendVerification } from "@/lib/api/auth";
import { Court4ApiError } from "@/lib/api/client";

const refreshUser = vi.fn();
const verifyEmail = vi.fn();
const logout = vi.fn();
const replace = vi.fn();
const authState = {
  user: {
    email: "player@example.com",
    email_verified_at: null as string | null,
  } as { email: string; email_verified_at: string | null } | null,
  loading: false,
};
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    ...authState,
    refreshUser,
    verifyEmail,
    logout,
  }),
}));
vi.mock("@/lib/api/auth", () => ({
  resendVerification: vi.fn(),
}));

describe("email verification UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = { email: "player@example.com", email_verified_at: null };
    window.history.replaceState(null, "", "/verify-email?token=secret");
  });

  it("shows the pending state and resends verification", async () => {
    vi.mocked(resendVerification).mockResolvedValue({
      verified: false,
      message: "A new verification link has been sent.",
      user: null,
    });
    render(<VerificationPending />);
    expect(screen.getByText("ACCOUNT ACTIVATION")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Verify your email" })).toBeVisible();
    expect(screen.getByText(/created\. Verify your email to continue/)).toBeVisible();
    expect(screen.queryByText(/browse your account/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /continue to court4/i })).not.toBeInTheDocument();
    expect(screen.getByText(/player@example.com/)).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Resend verification email" }),
    );
    expect(await screen.findByText("A new verification link has been sent.")).toBeVisible();
  });

  it("refreshes status and remains gated when verification is not confirmed", async () => {
    refreshUser.mockResolvedValueOnce({
      email: "player@example.com",
      email_verified_at: null,
    });
    render(<VerificationPending />);
    await userEvent.click(screen.getByRole("button", { name: "I’ve verified my email" }));
    expect(refreshUser).toHaveBeenCalledOnce();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We haven’t confirmed your email yet",
    );
    expect(replace).not.toHaveBeenCalledWith("/dashboard");
  });

  it("refreshes status and opens Dashboard after another browser verifies", async () => {
    refreshUser.mockResolvedValueOnce({
      email: "player@example.com",
      email_verified_at: "2026-08-04T00:00:00Z",
    });
    render(<VerificationPending />);
    await userEvent.click(screen.getByRole("button", { name: "I’ve verified my email" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("establishes the session, removes the token URL, and opens Dashboard", async () => {
    verifyEmail.mockResolvedValueOnce("Your email has been verified.");
    const view = render(<VerifyEmail token="valid-token" />);
    await waitFor(() => {
      expect(verifyEmail).toHaveBeenCalledWith("valid-token");
      expect(replace).toHaveBeenCalledWith("/dashboard");
    });
    expect(window.location.pathname).toBe("/verify-email");
    expect(window.location.search).toBe("");
    expect(screen.queryByRole("link", { name: /log in/i })).not.toBeInTheDocument();

    view.unmount();
  });

  it("reports an expired link safely and offers an authenticated resend", async () => {
    verifyEmail.mockRejectedValueOnce(
      new Court4ApiError("This link has expired. Request a new one.", {
        code: "token_expired",
        status: 400,
      }),
    );
    render(<VerifyEmail token="expired-token" />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("This link has expired");
    });
    expect(screen.queryByText(/provider/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request another link/i })).toHaveAttribute(
      "href",
      "/verification-pending",
    );
  });

  it("requires explicit logout before verifying a different account", async () => {
    verifyEmail.mockRejectedValueOnce(
      new Court4ApiError("This verification link belongs to a different Court4 account.", {
        code: "verification_account_mismatch",
        status: 409,
      }),
    );
    logout.mockResolvedValueOnce(undefined);
    verifyEmail.mockResolvedValueOnce("Your email has been verified.");
    render(<VerifyEmail token="other-account-token" />);

    await userEvent.click(
      await screen.findByRole("button", { name: /log out and verify this account/i }),
    );
    await waitFor(() => expect(verifyEmail).toHaveBeenCalledTimes(2));
    expect(logout).toHaveBeenCalledOnce();
  });
});
