import { beforeEach, describe, expect, it } from "vitest";

import {
  emptyPlayerProfile,
  getPlayerProfile,
  LEGACY_PLAYER_PROFILE_STORAGE_KEY,
  playerProfileStorageKey,
  savePlayerProfile,
  validateProfileImageFile,
  validatePlayerProfile,
} from "@/lib/player-profile";

const playerOneId = "56ae6283-69ee-44b6-9f19-6bf9dc1d7092";
const playerTwoId = "57bd7394-70ff-45c7-8a20-7ca0ed2e8103";

describe("player profile storage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns an empty browser-local profile by default", () => {
    expect(getPlayerProfile(playerOneId)).toEqual(emptyPlayerProfile);
  });

  it("trims and sanitizes explicitly entered values before saving", () => {
    const saved = savePlayerProfile(playerOneId, {
      displayName: "  <Ava>  Court4  ",
      dominantHand: "right",
      experienceLevel: "competitive",
      homeClub: "  <Downtown>  Courts  ",
      profileImageDataUrl: "",
    });

    expect(saved).toMatchObject({
      displayName: "Ava Court4",
      dominantHand: "right",
      experienceLevel: "competitive",
      homeClub: "Downtown Courts",
    });
    expect(getPlayerProfile(playerOneId)).toEqual(saved);
  });

  it("filters malformed stored profile fields", () => {
    window.localStorage.setItem(
      playerProfileStorageKey(playerOneId),
      JSON.stringify({
        displayName: "<script>alert(1)</script>",
        dominantHand: "both",
        experienceLevel: "expert",
        homeClub: 123,
        profileImageDataUrl: "javascript:alert(1)",
      }),
    );

    expect(getPlayerProfile(playerOneId)).toEqual({
      displayName: "scriptalert(1)/script",
      dominantHand: "prefer_not_to_say",
      experienceLevel: "prefer_not_to_say",
      homeClub: "",
      profileImageDataUrl: "",
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

  it("persists a safe profile photo data URL", () => {
    const profileImageDataUrl = "data:image/png;base64,AQID";

    const saved = savePlayerProfile(playerOneId, {
      ...emptyPlayerProfile,
      displayName: "Alexis",
      profileImageDataUrl,
    });

    expect(saved.profileImageDataUrl).toBe(profileImageDataUrl);
    expect(getPlayerProfile(playerOneId).profileImageDataUrl).toBe(profileImageDataUrl);
  });

  it("keeps profile details and photos isolated between accounts", () => {
    savePlayerProfile(playerOneId, {
      ...emptyPlayerProfile,
      displayName: "Alexis",
      profileImageDataUrl: "data:image/png;base64,AQID",
    });

    expect(getPlayerProfile(playerTwoId)).toEqual(emptyPlayerProfile);

    savePlayerProfile(playerTwoId, {
      ...emptyPlayerProfile,
      displayName: "Mimi",
    });

    expect(getPlayerProfile(playerOneId)).toMatchObject({
      displayName: "Alexis",
      profileImageDataUrl: "data:image/png;base64,AQID",
    });
    expect(getPlayerProfile(playerTwoId)).toMatchObject({
      displayName: "Mimi",
      profileImageDataUrl: "",
    });
  });

  it("does not expose the legacy unscoped profile to an account", () => {
    window.localStorage.setItem(
      LEGACY_PLAYER_PROFILE_STORAGE_KEY,
      JSON.stringify({
        ...emptyPlayerProfile,
        displayName: "Previous browser user",
        profileImageDataUrl: "data:image/png;base64,AQID",
      }),
    );

    expect(getPlayerProfile(playerOneId)).toEqual(emptyPlayerProfile);
  });

  it("rejects unsupported or oversized profile photo files", () => {
    expect(validateProfileImageFile(new File(["gif"], "avatar.gif", { type: "image/gif" }))).toBe(
      "Choose a JPEG, PNG, or WebP image.",
    );
    expect(
      validateProfileImageFile(
        new File([new Uint8Array(5_000_000)], "avatar.jpg", { type: "image/jpeg" }),
      ),
    ).toBeNull();
    expect(
      validateProfileImageFile(
        new File([new Uint8Array(10_000_001)], "avatar.png", { type: "image/png" }),
      ),
    ).toBe("Profile photo must be 10 MB or smaller.");
  });

  it("recognizes supported image extensions when the browser omits the MIME type", () => {
    expect(validateProfileImageFile(new File(["photo"], "avatar.JPEG"))).toBeNull();
  });
});
