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

  it("renders all six primary navigation items with expected routes", () => {
    renderWithQueryClient(<AppShell>Workspace</AppShell>);

    const navigation = screen.getAllByRole("navigation", { name: "Primary navigation" })[0];
    expect(within(navigation).getByRole("link", { name: /dashboard/i })).toHaveAttribute(
      "href",
      "/",
    );
    expect(within(navigation).getByRole("link", { name: /performance/i })).toHaveAttribute(
      "href",
      "/performance",
    );
    expect(within(navigation).getByRole("link", { name: /^matches$/i })).toHaveAttribute(
      "href",
      "/matches",
    );
    expect(within(navigation).getByRole("link", { name: /upload match/i })).toHaveAttribute(
      "href",
      "/matches/upload",
    );
    expect(within(navigation).getByRole("link", { name: /^player$/i })).toHaveAttribute(
      "href",
      "/player",
    );
    expect(within(navigation).getByRole("link", { name: /settings/i })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("marks the active route clearly", () => {
    pathnameMock.mockReturnValue("/performance");

    renderWithQueryClient(<AppShell>Performance</AppShell>);

    expect(screen.getAllByRole("link", { name: /performance/i })[0]).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("uses the saved display name in the shell", async () => {
    savePlayerProfile({
      displayName: "Ava",
      dominantHand: "right",
      experienceLevel: "advanced",
      homeClub: "",
    });

    renderWithQueryClient(<AppShell>Dashboard</AppShell>);

    expect(await screen.findAllByText("Ava")).not.toHaveLength(0);
  });
});
