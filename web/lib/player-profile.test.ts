import { beforeEach, describe, expect, it } from "vitest";

import {
  emptyPlayerProfile,
  getPlayerProfile,
  PLAYER_PROFILE_STORAGE_KEY,
  savePlayerProfile,
  validatePlayerProfile,
} from "@/lib/player-profile";

describe("player profile storage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns an empty browser-local profile by default", () => {
    expect(getPlayerProfile()).toEqual(emptyPlayerProfile);
  });

  it("trims and sanitizes explicitly entered values before saving", () => {
    const saved = savePlayerProfile({
      displayName: "  <Ava>  Court4  ",
      dominantHand: "right",
      experienceLevel: "competitive",
      homeClub: "  <Downtown>  Courts  ",
    });

    expect(saved).toMatchObject({
      displayName: "Ava Court4",
      dominantHand: "right",
      experienceLevel: "competitive",
      homeClub: "Downtown Courts",
    });
    expect(getPlayerProfile()).toEqual(saved);
  });

  it("filters malformed stored profile fields", () => {
    window.localStorage.setItem(
      PLAYER_PROFILE_STORAGE_KEY,
      JSON.stringify({
        displayName: "<script>alert(1)</script>",
        dominantHand: "both",
        experienceLevel: "expert",
        homeClub: 123,
      }),
    );

    expect(getPlayerProfile()).toEqual({
      displayName: "scriptalert(1)/script",
      dominantHand: "prefer_not_to_say",
      experienceLevel: "prefer_not_to_say",
      homeClub: "",
    });
  });

  it("validates profile field lengths", () => {
    expect(
      validatePlayerProfile({
        ...emptyPlayerProfile,
        displayName: "a".repeat(37),
        homeClub: "b".repeat(81),
      }),
    ).toMatchObject({
      displayName: "Display name must be 36 characters or fewer.",
      homeClub: "Home club or location must be 80 characters or fewer.",
    });
  });
});
