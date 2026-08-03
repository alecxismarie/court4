import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PlayerProfilePage } from "@/components/player-profile-page";
import { playerProfileStorageKey } from "@/lib/player-profile";
import { renderWithQueryClient } from "@/test/render";

const authUserId = vi.hoisted(() => "56ae6283-69ee-44b6-9f19-6bf9dc1d7092");

vi.mock("@/lib/auth-context", () => ({
  useOptionalAuth: () => ({ user: { id: authUserId } }),
}));

describe("player profile page", () => {
  it("uses concise profile copy without repetitive headings", () => {
    renderWithQueryClient(<PlayerProfilePage />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Player profile" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Update the photo and details used across Court4.")).toBeInTheDocument();
    expect(screen.queryByText("Profile preview")).not.toBeInTheDocument();
    expect(screen.queryByText(/saved only in this browser/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/profile data is stored/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/does not make this profile public/i)).not.toBeInTheDocument();
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
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
    const stored = JSON.parse(
      window.localStorage.getItem(playerProfileStorageKey(authUserId)) ?? "{}",
    );
    expect(stored).toMatchObject({
      displayName: "Ava Smith",
      dominantHand: "left",
      experienceLevel: "advanced",
      homeClub: "Main Club",
    });
    expect(screen.getByRole("textbox", { name: /display name/i })).toHaveValue("Ava Smith");
    expect(screen.getByRole("img", { name: "Ava Smith profile photo" })).toBeInTheDocument();
    expect(screen.queryByText("<Ava>")).not.toBeInTheDocument();
  });

  it("selects, previews, saves, and removes a profile photo", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<PlayerProfilePage />);
    const photo = new File([new Uint8Array([1, 2, 3])], "alexis.png", {
      type: "image/png",
    });

    await user.upload(screen.getByLabelText("Profile photo"), photo);

    expect(await screen.findAllByRole("img", { name: "Player profile photo" })).toHaveLength(1);
    expect(screen.getByText("Change photo")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => {
      const stored = JSON.parse(
        window.localStorage.getItem(playerProfileStorageKey(authUserId)) ?? "{}",
      );
      expect(stored.profileImageDataUrl).toBe("data:image/png;base64,AQID");
    });

    await user.click(screen.getByRole("button", { name: /remove photo/i }));
    expect(screen.queryByRole("button", { name: /remove photo/i })).not.toBeInTheDocument();
  });

  it("rejects an unsupported profile photo format", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderWithQueryClient(<PlayerProfilePage />);

    await user.upload(
      screen.getByLabelText("Profile photo"),
      new File(["gif"], "alexis.gif", { type: "image/gif" }),
    );

    expect(
      await screen.findByText("Choose a JPEG, PNG, or WebP image."),
    ).toBeInTheDocument();
  });

  it("validates display name length before saving", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<PlayerProfilePage />);

    await user.type(screen.getByRole("textbox", { name: /display name/i }), "A".repeat(37));
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(
      await screen.findByText("Display name must be 36 characters or fewer."),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem(playerProfileStorageKey(authUserId))).toBeNull();
  });

  it("allows optional player fields to be cleared", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<PlayerProfilePage />);

    const homeClubInput = screen.getByRole("textbox", { name: /home club or location/i });
    await user.type(homeClubInput, "Court 4 Club");
    await user.click(screen.getByRole("button", { name: /save changes/i }));
    await screen.findByText("Profile saved.");

    await user.clear(homeClubInput);
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      const stored = JSON.parse(
        window.localStorage.getItem(playerProfileStorageKey(authUserId)) ?? "{}",
      );
      expect(stored.homeClub).toBe("");
    });
    expect(homeClubInput).toHaveValue("");
  });
});
