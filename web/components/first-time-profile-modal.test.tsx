import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FirstTimeProfileModal } from "@/components/first-time-profile-modal";
import { emptyPlayerProfile } from "@/lib/player-profile";
import {
  isPlayerOnboardingPending,
  markPlayerOnboardingPending,
} from "@/lib/profile-onboarding";

const userId = "56ae6283-69ee-44b6-9f19-6bf9dc1d7092";

describe("first-time player profile modal", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("collects and saves a display name for a newly registered player", async () => {
    const user = userEvent.setup();
    const saveProfile = vi.fn((profile) => profile);
    const onComplete = vi.fn();
    markPlayerOnboardingPending(userId);

    render(
      <FirstTimeProfileModal
        userId={userId}
        profile={emptyPlayerProfile}
        isProfileLoaded
        saveProfile={saveProfile}
        onComplete={onComplete}
      />,
    );

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What should we call you?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done" })).toBeDisabled();

    await user.type(
      screen.getByRole("textbox", { name: "What should we call you?" }),
      "  Alexis  ",
    );

    expect(screen.getByRole("heading", { name: "Welcome, Alexis!" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Done" }));

    expect(saveProfile).toHaveBeenCalledWith({
      ...emptyPlayerProfile,
      displayName: "Alexis",
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(isPlayerOnboardingPending(userId)).toBe(false);
    expect(onComplete).toHaveBeenCalledOnce();
  });

  it("does not appear for an account without a first-signup marker", () => {
    render(
      <FirstTimeProfileModal
        userId={userId}
        profile={emptyPlayerProfile}
        isProfileLoaded
        saveProfile={vi.fn()}
      />,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("recovers a new account without copying an ambiguous legacy profile", async () => {
    render(
      <FirstTimeProfileModal
        userId={userId}
        profile={emptyPlayerProfile}
        isProfileLoaded
        isNewAccount
        saveProfile={vi.fn()}
      />,
    );

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});
