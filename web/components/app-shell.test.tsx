import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import { savePlayerProfile } from "@/lib/player-profile";
import { renderWithQueryClient } from "@/test/render";

const pathnameMock = vi.hoisted(() => vi.fn(() => "/dashboard"));
const authUserId = vi.hoisted(() => "56ae6283-69ee-44b6-9f19-6bf9dc1d7092");
const authState = vi.hoisted(() => ({
  loading: false,
  user: {
    id: "56ae6283-69ee-44b6-9f19-6bf9dc1d7092",
    email: "player@example.com",
    email_verified_at: "2026-08-04T00:00:00Z" as string | null,
  },
  logout: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: pathnameMock,
}));

vi.mock("@/lib/auth-context", () => ({
  useOptionalAuth: () => authState,
}));

describe("app shell navigation", () => {
  beforeEach(() => {
    window.localStorage.clear();
    pathnameMock.mockReturnValue("/dashboard");
    authState.loading = false;
    authState.user.email_verified_at = "2026-08-04T00:00:00Z";
    authState.logout.mockReset();
  });

  it("does not expose private navigation to an unverified account", () => {
    authState.user.email_verified_at = null;
    renderWithQueryClient(<AppShell>Activation redirect</AppShell>);
    expect(screen.queryByRole("navigation", { name: "Primary navigation" })).not.toBeInTheDocument();
    expect(screen.getByText("Activation redirect")).toBeVisible();
  });

  it("renders the six player-facing navigation items with expected routes", () => {
    renderWithQueryClient(<AppShell>Workspace</AppShell>);

    const navigation = screen.getAllByRole("navigation", { name: "Primary navigation" })[1];
    expect(within(navigation).getByRole("link", { name: /dashboard/i })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(within(navigation).getByRole("link", { name: /^player$/i })).toHaveAttribute(
      "href",
      "/player",
    );
    expect(within(navigation).getByRole("link", { name: /my progress/i })).toHaveAttribute(
      "href",
      "/my-progress",
    );
    expect(within(navigation).getByRole("link", { name: /analysis history/i })).toHaveAttribute(
      "href",
      "/analysis-history",
    );
    expect(within(navigation).getByRole("link", { name: /upload match/i })).toHaveAttribute(
      "href",
      "/upload-match",
    );
    expect(within(navigation).getByRole("link", { name: /settings/i })).toHaveAttribute(
      "href",
      "/settings",
    );
    expect(
      within(navigation).queryByRole("link", { name: /calibration readiness/i }),
    ).not.toBeInTheDocument();
    expect(within(navigation).queryByRole("link", { name: /active play/i })).not.toBeInTheDocument();
  });

  it("uses a compact four-destination mobile navigation", () => {
    renderWithQueryClient(<AppShell>Workspace</AppShell>);

    const navigation = screen.getAllByRole("navigation", {
      name: "Primary navigation",
    })[0];
    expect(
      within(navigation)
        .getAllByRole("link")
        .map((link) => link.textContent?.trim()),
    ).toEqual(["Dashboard", "Upload", "History", "Progress"]);
    expect(within(navigation).queryByRole("link", { name: "Player" })).not.toBeInTheDocument();
    expect(within(navigation).queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("opens the mobile player menu and logs out", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<AppShell>Workspace</AppShell>);

    const accountButton = screen.getByRole("button", {
      name: "Open account menu for Local Player",
    });
    expect(accountButton).toHaveAttribute("aria-expanded", "false");
    await user.click(accountButton);

    const menu = screen.getByRole("menu", { name: "Player account" });
    expect(accountButton).toHaveAttribute("aria-expanded", "true");
    expect(within(menu).getByRole("menuitem", { name: "Player profile" })).toHaveAttribute(
      "href",
      "/player",
    );
    expect(within(menu).getByRole("menuitem", { name: "Settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
    await user.click(within(menu).getByRole("menuitem", { name: "Log out" }));
    expect(authState.logout).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu", { name: "Player account" })).not.toBeInTheDocument();
  });

  it("marks the active route clearly", () => {
    pathnameMock.mockReturnValue("/my-progress");

    renderWithQueryClient(<AppShell>My Progress</AppShell>);

    expect(screen.getAllByRole("link", { name: /my progress/i })[0]).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("marks Analysis History active on a nested match analytics route", () => {
    pathnameMock.mockReturnValue("/matches/analysis-123/analytics");

    renderWithQueryClient(<AppShell>Match IQ</AppShell>);

    for (const analysisHistoryLink of screen.getAllByRole("link", {
      name: /analysis history/i,
    })) {
      expect(analysisHistoryLink).toHaveAttribute("aria-current", "page");
      expect(analysisHistoryLink).toHaveClass("bg-court-lime");
    }
    for (const progressLink of screen.getAllByRole("link", { name: /my progress/i })) {
      expect(progressLink).not.toHaveAttribute("aria-current");
    }
  });

  it("keeps desktop navigation items on separate rows", () => {
    renderWithQueryClient(<AppShell>Workspace</AppShell>);

    const desktopNavigation = screen.getAllByRole("navigation", {
      name: "Primary navigation",
    })[1];
    for (const link of within(desktopNavigation).getAllByRole("link")) {
      expect(link).toHaveClass("w-full");
    }
  });

  it("uses the required player navigation order", () => {
    renderWithQueryClient(<AppShell>Workspace</AppShell>);

    const desktopNavigation = screen.getAllByRole("navigation", {
      name: "Primary navigation",
    })[1];
    expect(
      within(desktopNavigation)
        .getAllByRole("link")
        .map((link) => link.textContent?.trim()),
    ).toEqual([
      "Dashboard",
      "Player",
      "Upload Match",
      "Analysis History",
      "My Progress",
      "Settings",
    ]);
  });

  it("centers the desktop logo above navigation", () => {
    renderWithQueryClient(<AppShell>Workspace</AppShell>);

    const desktopLogo = screen.getAllByRole("link", {
      name: "Court4 dashboard",
    })[1];
    expect(desktopLogo).toHaveClass("flex", "justify-center");
  });

  it("uses the saved display name in the shell", async () => {
    savePlayerProfile(authUserId, {
      displayName: "Ava",
      dominantHand: "right",
      experienceLevel: "advanced",
      homeClub: "",
      profileImageDataUrl: "",
    });

    renderWithQueryClient(<AppShell>Dashboard</AppShell>);

    expect(await screen.findAllByText("Ava")).not.toHaveLength(0);
  });
});
