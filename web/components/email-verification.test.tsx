import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VerificationPending, VerifyEmail } from "@/components/email-verification";
import { resendVerification, verifyEmail } from "@/lib/api/auth";
import { Court4ApiError } from "@/lib/api/client";

const refreshUser = vi.fn();
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: {
      email: "player@example.com",
      email_verified_at: null,
    },
    refreshUser,
  }),
}));
vi.mock("@/lib/api/auth", () => ({
  resendVerification: vi.fn(),
  verifyEmail: vi.fn(),
}));

describe("email verification UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the pending state and resends verification", async () => {
    vi.mocked(resendVerification).mockResolvedValue({
      verified: false,
      message: "A new verification link has been sent.",
      user: null,
    });
    render(<VerificationPending />);
    expect(screen.getByText(/player@example.com/)).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Resend verification email" }),
    );
    expect(await screen.findByText("A new verification link has been sent.")).toBeVisible();
  });

  it("completes verification and reports an expired link safely", async () => {
    vi.mocked(verifyEmail).mockResolvedValueOnce({
      verified: true,
      message: "Your email has been verified.",
      user: null,
    });
    const view = render(<VerifyEmail token="valid-token" />);
    expect(await screen.findByText("Your email has been verified.")).toBeVisible();

    view.unmount();
    vi.mocked(verifyEmail).mockRejectedValueOnce(
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
  });
});
