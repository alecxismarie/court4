const STORAGE_KEY = "court4.recentAnalyses";
export const RECENT_ANALYSES_UPDATED_EVENT = "court4:recent-analyses-updated";
const MAX_RECENT_ANALYSES = 10;
const ANALYSIS_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;

export function getRecentAnalysisIds(): string[] {
  const storage = safeStorage();
  if (!storage) {
    return [];
  }
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter((value): value is string => typeof value === "string")
      .filter((value) => ANALYSIS_ID_PATTERN.test(value))
      .slice(0, MAX_RECENT_ANALYSES);
  } catch {
    return [];
  }
}

export function rememberAnalysisId(analysisId: string): void {
  if (!ANALYSIS_ID_PATTERN.test(analysisId)) {
    return;
  }
  const storage = safeStorage();
  if (!storage) {
    return;
  }
  const next = [
    analysisId,
    ...getRecentAnalysisIds().filter((storedId) => storedId !== analysisId),
  ].slice(0, MAX_RECENT_ANALYSES);
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(next));
    window.dispatchEvent(new Event(RECENT_ANALYSES_UPDATED_EVENT));
  } catch {
    // Browser storage can be disabled or quota-limited.
  }
}

function safeStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const storage = window.localStorage;
    const probe = "__court4_storage_probe__";
    storage.setItem(probe, probe);
    storage.removeItem(probe);
    return storage;
  } catch {
    return null;
  }
}
