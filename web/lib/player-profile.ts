export const PLAYER_PROFILE_STORAGE_KEY = "court4.playerProfile";
export const PLAYER_PROFILE_UPDATED_EVENT = "court4:player-profile-updated";
export const MAX_PROFILE_IMAGE_BYTES = 10_000_000;
export const PROFILE_IMAGE_ACCEPT = ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp";

const MAX_STORED_PROFILE_IMAGE_BYTES = 1_000_000;
const MAX_PROFILE_IMAGE_DIMENSION = 512;
const PROFILE_IMAGE_OUTPUT_QUALITY = 0.84;
const supportedProfileImageTypes = ["image/jpeg", "image/jpg", "image/png", "image/webp"];
const supportedProfileImageExtensions = [".jpg", ".jpeg", ".png", ".webp"];

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
  profileImageDataUrl: string;
};

export type PlayerProfileErrors = Partial<Record<keyof PlayerProfile, string>>;

export const emptyPlayerProfile: PlayerProfile = {
  displayName: "",
  dominantHand: "prefer_not_to_say",
  experienceLevel: "prefer_not_to_say",
  homeClub: "",
  profileImageDataUrl: "",
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
    profileImageDataUrl: isSafeProfileImageDataUrl(profile.profileImageDataUrl)
      ? profile.profileImageDataUrl
      : "",
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
    profileImageDataUrl:
      typeof raw.profileImageDataUrl === "string" ? raw.profileImageDataUrl : "",
  });
}

export function validateProfileImageFile(file: File): string | null {
  const normalizedType = file.type.toLowerCase();
  const normalizedName = file.name.toLowerCase();
  if (
    !supportedProfileImageTypes.includes(normalizedType) &&
    !supportedProfileImageExtensions.some((extension) => normalizedName.endsWith(extension))
  ) {
    return "Choose a JPEG, PNG, or WebP image.";
  }
  if (file.size > MAX_PROFILE_IMAGE_BYTES) {
    return "Profile photo must be 10 MB or smaller.";
  }
  return null;
}

export async function readProfileImageFile(file: File): Promise<string> {
  const needsOptimization =
    file.size > MAX_STORED_PROFILE_IMAGE_BYTES ||
    !supportedProfileImageTypes.includes(file.type.toLowerCase());
  if (needsOptimization) {
    return optimizeProfileImageFile(file);
  }
  return readFileAsDataUrl(file);
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      if (typeof reader.result === "string" && isSafeProfileImageDataUrl(reader.result)) {
        resolve(reader.result);
        return;
      }
      reject(new Error("Profile photo could not be read."));
    });
    reader.addEventListener("error", () => reject(new Error("Profile photo could not be read.")));
    reader.readAsDataURL(file);
  });
}

async function optimizeProfileImageFile(file: File): Promise<string> {
  const objectUrl = URL.createObjectURL(file);
  try {
    const image = await loadProfileImage(objectUrl);
    const largestSourceDimension = Math.max(image.naturalWidth, image.naturalHeight);
    if (largestSourceDimension <= 0) {
      throw new Error("Profile photo could not be read.");
    }
    for (const maximumDimension of [MAX_PROFILE_IMAGE_DIMENSION, 384, 256]) {
      const scale = Math.min(1, maximumDimension / largestSourceDimension);
      const width = Math.max(1, Math.round(image.naturalWidth * scale));
      const height = Math.max(1, Math.round(image.naturalHeight * scale));
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (!context) {
        throw new Error("Profile photo could not be read.");
      }
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = "high";
      context.drawImage(image, 0, 0, width, height);
      const optimized = canvas.toDataURL("image/webp", PROFILE_IMAGE_OUTPUT_QUALITY);
      if (isSafeProfileImageDataUrl(optimized)) {
        return optimized;
      }
    }
    throw new Error("Profile photo could not be reduced to a safe size.");
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function loadProfileImage(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.decoding = "async";
    image.addEventListener("load", () => resolve(image), { once: true });
    image.addEventListener(
      "error",
      () => reject(new Error("Profile photo could not be read.")),
      { once: true },
    );
    image.src = source;
  });
}

function sanitizeText(value: string): string {
  return value.replace(/[<>]/g, "").replace(/\s+/g, " ").trim();
}

function isSafeProfileImageDataUrl(value: string): boolean {
  if (
    !value ||
    value.length > Math.ceil((MAX_STORED_PROFILE_IMAGE_BYTES * 4) / 3) + 100
  ) {
    return false;
  }
  return /^data:image\/(?:jpe?g|png|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(value);
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
