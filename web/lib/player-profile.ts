export const PLAYER_PROFILE_STORAGE_KEY = "court4.playerProfile";
export const PLAYER_PROFILE_UPDATED_EVENT = "court4:player-profile-updated";

export const dominantHandOptions = ["right", "left", "prefer_not_to_say"] as const;
export const experienceLevelOptions = [
  "beginner",
  "intermediate",
  "advanced",
  "competitive",
  "prefer_not_to_say",
] as const;

export type DominantHand = (typeof dominantHandOptions)[number];
export type ExperienceLevel = (typeof experienceLevelOptions)[number];

export type PlayerProfile = {
  displayName: string;
  dominantHand: DominantHand;
  experienceLevel: ExperienceLevel;
  homeClub: string;
};

export type PlayerProfileErrors = Partial<Record<keyof PlayerProfile, string>>;

export const emptyPlayerProfile: PlayerProfile = {
  displayName: "",
  dominantHand: "prefer_not_to_say",
  experienceLevel: "prefer_not_to_say",
  homeClub: "",
};

const MAX_DISPLAY_NAME_LENGTH = 36;
const MAX_HOME_CLUB_LENGTH = 80;

export function getPlayerProfile(): PlayerProfile {
  const storage = safeStorage();
  if (!storage) {
    return emptyPlayerProfile;
  }

  try {
    const raw = storage.getItem(PLAYER_PROFILE_STORAGE_KEY);
    if (!raw) {
      return emptyPlayerProfile;
    }
    return parsePlayerProfile(JSON.parse(raw));
  } catch {
    return emptyPlayerProfile;
  }
}

export function savePlayerProfile(profile: PlayerProfile): PlayerProfile {
  const normalized = normalizePlayerProfile(profile);
  const errors = validatePlayerProfile(normalized);
  if (Object.keys(errors).length > 0) {
    throw new Error("Player profile is invalid.");
  }

  const storage = safeStorage();
  if (storage) {
    storage.setItem(PLAYER_PROFILE_STORAGE_KEY, JSON.stringify(normalized));
    window.dispatchEvent(new Event(PLAYER_PROFILE_UPDATED_EVENT));
  }
  return normalized;
}

export function validatePlayerProfile(profile: PlayerProfile): PlayerProfileErrors {
  const normalized = normalizePlayerProfile(profile);
  const errors: PlayerProfileErrors = {};
  if (normalized.displayName.length > MAX_DISPLAY_NAME_LENGTH) {
    errors.displayName = `Display name must be ${MAX_DISPLAY_NAME_LENGTH} characters or fewer.`;
  }
  if (normalized.homeClub.length > MAX_HOME_CLUB_LENGTH) {
    errors.homeClub = `Home club or location must be ${MAX_HOME_CLUB_LENGTH} characters or fewer.`;
  }
  if (!isDominantHand(normalized.dominantHand)) {
    errors.dominantHand = "Choose a supported dominant hand option.";
  }
  if (!isExperienceLevel(normalized.experienceLevel)) {
    errors.experienceLevel = "Choose a supported experience level option.";
  }
  return errors;
}

export function normalizePlayerProfile(profile: PlayerProfile): PlayerProfile {
  return {
    displayName: sanitizeText(profile.displayName).slice(0, MAX_DISPLAY_NAME_LENGTH + 1),
    dominantHand: isDominantHand(profile.dominantHand)
      ? profile.dominantHand
      : "prefer_not_to_say",
    experienceLevel: isExperienceLevel(profile.experienceLevel)
      ? profile.experienceLevel
      : "prefer_not_to_say",
    homeClub: sanitizeText(profile.homeClub).slice(0, MAX_HOME_CLUB_LENGTH + 1),
  };
}

export function formatDominantHand(value: DominantHand): string {
  if (value === "right") {
    return "Right";
  }
  if (value === "left") {
    return "Left";
  }
  return "Prefer not to say";
}

export function formatExperienceLevel(value: ExperienceLevel): string {
  if (value === "prefer_not_to_say") {
    return "Prefer not to say";
  }
  return value.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function parsePlayerProfile(value: unknown): PlayerProfile {
  if (!value || typeof value !== "object") {
    return emptyPlayerProfile;
  }
  const raw = value as Partial<Record<keyof PlayerProfile, unknown>>;
  return normalizePlayerProfile({
    displayName: typeof raw.displayName === "string" ? raw.displayName : "",
    dominantHand:
      typeof raw.dominantHand === "string" && isDominantHand(raw.dominantHand)
        ? raw.dominantHand
        : "prefer_not_to_say",
    experienceLevel:
      typeof raw.experienceLevel === "string" &&
      isExperienceLevel(raw.experienceLevel)
        ? raw.experienceLevel
        : "prefer_not_to_say",
    homeClub: typeof raw.homeClub === "string" ? raw.homeClub : "",
  });
}

function sanitizeText(value: string): string {
  return value.replace(/[<>]/g, "").replace(/\s+/g, " ").trim();
}

function isDominantHand(value: string): value is DominantHand {
  return dominantHandOptions.some((option) => option === value);
}

function isExperienceLevel(value: string): value is ExperienceLevel {
  return experienceLevelOptions.some((option) => option === value);
}

function safeStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const storage = window.localStorage;
    const probe = "__court4_profile_storage_probe__";
    storage.setItem(probe, probe);
    storage.removeItem(probe);
    return storage;
  } catch {
    return null;
  }
}
