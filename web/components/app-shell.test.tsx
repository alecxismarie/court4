import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import { savePlayerProfile } from "@/lib/player-profile";
import { renderWithQueryClient } from "@/test/render";

const pathnameMock = vi.hoisted(() => vi.fn(() => "/"));

vi.mock("next/navigation", () => ({
  usePathname: pathnameMock,
}));

describe("app shell navigation", () => {
  beforeEach(() => {
    window.localStorage.clear();
    pathnameMock.mockReturnValue("/");
  });

  it("renders the six player-facing navigation items with expected routes", () => {
    renderWithQueryClient(<AppShell>Workspace</AppShell>);

    const navigation = screen.getAllByRole("navigation", { name: "Primary navigation" })[0];
    expect(within(navigation).getByRole("link", { name: /dashboard/i })).toHaveAttribute(
      "href",
      "/",
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

  it("marks the active route clearly", () => {
    pathnameMock.mockReturnValue("/my-progress");

    renderWithQueryClient(<AppShell>My Progress</AppShell>);

    expect(screen.getAllByRole("link", { name: /my progress/i })[0]).toHaveAttribute(
      "aria-current",
      "page",
    );
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
    savePlayerProfile({
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
