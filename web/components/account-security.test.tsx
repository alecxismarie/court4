import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccountSecurity } from "@/components/account-security";
import {
  changePassword,
  listSessions,
  revokeAllSessions,
  revokeSession,
} from "@/lib/api/auth";

const refreshUser = vi.fn().mockResolvedValue(undefined);
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: {
      email: "player@example.com",
      email_verified_at: "2026-07-31T00:00:00Z",
    },
    refreshUser,
    logout: vi.fn(),
  }),
}));
vi.mock("@/lib/api/auth", () => ({
  changePassword: vi.fn(),
  listSessions: vi.fn(),
  revokeAllSessions: vi.fn(),
  revokeSession: vi.fn(),
}));

const sessions = [
  {
    id: "e13c7d87-59f8-44ad-9ab6-843c2274a0b7",
    created_at: "2026-07-31T00:00:00Z",
    last_used_at: null,
    expires_at: "2026-08-30T00:00:00Z",
    revoked_at: null,
    client_label: "Chrome on Windows",
    current: true,
  },
  {
    id: "219b0d9b-067c-4dc9-871c-789e98c6a8b8",
    created_at: "2026-07-30T00:00:00Z",
    last_used_at: "2026-07-30T01:00:00Z",
    expires_at: "2026-08-29T00:00:00Z",
    revoked_at: null,
    client_label: "Firefox on Linux",
    current: false,
  },
];

describe("account security UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listSessions).mockResolvedValue(sessions);
  });

  it("lists sessions and revokes another browser", async () => {
    vi.mocked(revokeSession).mockResolvedValue(true);
    render(<AccountSecurity />);
    expect(await screen.findByText("Firefox on Linux")).toBeVisible();
    await userEvent.click(screen.getAllByRole("button", { name: "Sign out" })[0]);
    expect(revokeSession).toHaveBeenCalledWith(sessions[1].id);
  });

  it("changes password and revokes all other sessions", async () => {
    vi.mocked(changePassword).mockResolvedValue({} as never);
    vi.mocked(revokeAllSessions).mockResolvedValue(1);
    render(<AccountSecurity />);
    await screen.findByText("Chrome on Windows");

    await userEvent.type(
      screen.getByLabelText("Current password"),
      "a current long password",
    );
    await userEvent.type(
      screen.getByLabelText("New password"),
      "a replacement long password",
    );
    await userEvent.type(
      screen.getByLabelText("Confirm new password"),
      "a replacement long password",
    );
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText(/Other sessions were signed out/)).toBeVisible();

    await userEvent.click(
      screen.getByRole("button", { name: "Sign out all other sessions" }),
    );
    expect(revokeAllSessions).toHaveBeenCalledWith(true);
    expect(await screen.findByText("One other session was signed out.")).toBeVisible();
  });
});
