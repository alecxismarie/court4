export type LandingAuthMode = "login" | "signup";

const AUTH_ROUTE_PATHS = new Set([
  "/",
  "/login",
  "/register",
]);

export function safeInternalDestination(value: string | null | undefined): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return null;
  }
  let decoded: string;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return null;
  }
  if (
    decoded.startsWith("//") ||
    decoded.includes("\\") ||
    /^[a-z][a-z0-9+.-]*:/i.test(decoded.slice(1))
  ) {
    return null;
  }
  const pathname = decoded.split(/[?#]/, 1)[0];
  if (AUTH_ROUTE_PATHS.has(pathname)) return null;
  return value;
}

export function safeLandingDestination(value: string | null | undefined): string {
  return safeInternalDestination(value) ?? "/dashboard";
}

export function landingAuthHref(
  mode: LandingAuthMode,
  next: string | null | undefined,
): string {
  const params = new URLSearchParams({ auth: mode });
  const destination = safeInternalDestination(next);
  if (destination) params.set("next", destination);
  return `/?${params.toString()}`;
}
