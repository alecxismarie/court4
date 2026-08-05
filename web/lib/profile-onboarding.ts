const PLAYER_ONBOARDING_STORAGE_PREFIX = "court4.playerOnboarding.pending.";
const FIRST_WELCOME_STORAGE_PREFIX = "court4.playerOnboarding.firstWelcome.";

export function markPlayerOnboardingPending(userId: string): void {
  safeLocalStorage()?.setItem(pendingStorageKey(userId), "true");
  clearFirstPlayerWelcome(userId);
}

export function isPlayerOnboardingPending(userId: string): boolean {
  return safeLocalStorage()?.getItem(pendingStorageKey(userId)) === "true";
}

export function clearPlayerOnboardingPending(userId: string): void {
  safeLocalStorage()?.removeItem(pendingStorageKey(userId));
}

export function completePlayerOnboarding(userId: string): void {
  clearPlayerOnboardingPending(userId);
  safeSessionStorage()?.setItem(firstWelcomeStorageKey(userId), "true");
}

export function isFirstPlayerWelcome(userId: string): boolean {
  return safeSessionStorage()?.getItem(firstWelcomeStorageKey(userId)) === "true";
}

export function clearFirstPlayerWelcome(userId: string): void {
  safeSessionStorage()?.removeItem(firstWelcomeStorageKey(userId));
}

function pendingStorageKey(userId: string): string {
  return `${PLAYER_ONBOARDING_STORAGE_PREFIX}${userId}`;
}

function firstWelcomeStorageKey(userId: string): string {
  return `${FIRST_WELCOME_STORAGE_PREFIX}${userId}`;
}

function safeLocalStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function safeSessionStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}
