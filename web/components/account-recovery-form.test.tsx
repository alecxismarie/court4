import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ForgotPasswordForm,
  ResetPasswordForm,
} from "@/components/account-recovery-form";
import { forgotPassword, resetPassword } from "@/lib/api/auth";
import { Court4ApiError } from "@/lib/api/client";

vi.mock("@/lib/api/auth", () => ({
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
}));

describe("account recovery UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the same generic forgot-password response", async () => {
    vi.mocked(forgotPassword).mockResolvedValue(
      "If an active account exists for that email, a password reset link has been sent.",
    );
    render(<ForgotPasswordForm />);
    await userEvent.type(screen.getByLabelText("Email"), "unknown@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText(/If an active account exists/)).toBeVisible();
  });

  it("resets a password and renders a typed invalid-link error", async () => {
    vi.mocked(resetPassword).mockResolvedValueOnce(
      "Your password has been reset. Sign in with your new password.",
    );
    const view = render(<ResetPasswordForm token="valid" />);
    await userEvent.type(
      screen.getByLabelText("New password"),
      "a sufficiently long password",
    );
    await userEvent.type(
      screen.getByLabelText("Confirm new password"),
      "a sufficiently long password",
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByText(/Sign in with your new password/)).toBeVisible();

    view.unmount();
    vi.mocked(resetPassword).mockRejectedValueOnce(
      new Court4ApiError("This link is invalid or has already been used.", {
        code: "invalid_or_used_token",
        status: 400,
      }),
    );
    render(<ResetPasswordForm token="used" />);
    await userEvent.type(
      screen.getByLabelText("New password"),
      "another sufficiently long password",
    );
    await userEvent.type(
      screen.getByLabelText("Confirm new password"),
      "another sufficiently long password",
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "invalid or has already been used",
    );
  });
});
