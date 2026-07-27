import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { PlayerProfilePage } from "@/components/player-profile-page";
import { PLAYER_PROFILE_STORAGE_KEY } from "@/lib/player-profile";
import { renderWithQueryClient } from "@/test/render";

describe("player profile page", () => {
  it("explains the browser-local profile without repetitive headings", () => {
    renderWithQueryClient(<PlayerProfilePage />);

    expect(screen.getByText("Your details")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Player profile" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/saved only in this browser—not to an account/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Your player profile" }),
    ).not.toBeInTheDocument();
  });

  beforeEach(() => {
    window.localStorage.clear();
  });

  it("saves trimmed and sanitized browser-local profile details", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<PlayerProfilePage />);

    await user.type(screen.getByRole("textbox", { name: /display name/i }), "  <Ava>   Smith  ");
    await user.selectOptions(screen.getByLabelText(/dominant hand/i), "left");
    await user.selectOptions(screen.getByLabelText(/experience level/i), "advanced");
    await user.type(screen.getByRole("textbox", { name: /home club or location/i }), "  <Main>   Club  ");
    await user.click(screen.getByRole("button", { name: /save player profile/i }));

    expect(await screen.findByText("Player profile saved in this browser.")).toBeInTheDocument();
    const stored = JSON.parse(window.localStorage.getItem(PLAYER_PROFILE_STORAGE_KEY) ?? "{}");
    expect(stored).toMatchObject({
      displayName: "Ava Smith",
      dominantHand: "left",
      experienceLevel: "advanced",
      homeClub: "Main Club",
    });
    expect(screen.getByText("Ava Smith")).toBeInTheDocument();
    expect(screen.queryByText("<Ava>")).not.toBeInTheDocument();
  });

  it("validates display name length before saving", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<PlayerProfilePage />);

    await user.type(screen.getByRole("textbox", { name: /display name/i }), "A".repeat(37));
    await user.click(screen.getByRole("button", { name: /save player profile/i }));

    expect(
      await screen.findByText("Display name must be 36 characters or fewer."),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem(PLAYER_PROFILE_STORAGE_KEY)).toBeNull();
  });

  it("allows optional player fields to be cleared", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<PlayerProfilePage />);

    const homeClubInput = screen.getByRole("textbox", { name: /home club or location/i });
    await user.type(homeClubInput, "Court 4 Club");
    await user.click(screen.getByRole("button", { name: /save player profile/i }));
    await screen.findByText("Player profile saved in this browser.");

    await user.clear(homeClubInput);
    await user.click(screen.getByRole("button", { name: /save player profile/i }));

    await waitFor(() => {
      const stored = JSON.parse(window.localStorage.getItem(PLAYER_PROFILE_STORAGE_KEY) ?? "{}");
      expect(stored.homeClub).toBe("");
    });
    expect(screen.getAllByText("Not set").length).toBeGreaterThan(0);
  });
});
