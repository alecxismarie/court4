import { beforeEach, describe, expect, it } from "vitest";

import {
  completePlayerOnboarding,
  clearFirstPlayerWelcome,
  isFirstPlayerWelcome,
  isPlayerOnboardingPending,
  markPlayerOnboardingPending,
} from "@/lib/profile-onboarding";

describe("player onboarding state", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("tracks pending onboarding separately for each account", () => {
    markPlayerOnboardingPending("player-one");

    expect(isPlayerOnboardingPending("player-one")).toBe(true);
    expect(isPlayerOnboardingPending("player-two")).toBe(false);

    completePlayerOnboarding("player-one");
    expect(isPlayerOnboardingPending("player-one")).toBe(false);
    expect(isFirstPlayerWelcome("player-one")).toBe(true);

    clearFirstPlayerWelcome("player-one");
    expect(isFirstPlayerWelcome("player-one")).toBe(false);
  });
});
