import { z } from "zod";

import {
  apiErrorFromResponse,
  authenticatedFetch,
  refreshAccessToken,
  requestJson,
  setAccessToken,
  toApiUrl,
} from "@/lib/api/client";

export const userSchema = z.object({
  id: z.string().uuid(),
  email: z.string(),
  account_status: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  last_login_at: z.string().nullable(),
  email_verified_at: z.string().nullable(),
  password_changed_at: z.string().nullable(),
  display_name: z.string().nullable(),
  verification_delivery_mode: z
    .enum(["external", "development", "unavailable"])
    .nullable()
    .optional(),
});

export const authResponseSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal("bearer"),
  expires_in: z.number().positive(),
  user: userSchema,
});

export type AuthUser = z.infer<typeof userSchema>;
export type AuthResponse = z.infer<typeof authResponseSchema>;

const messageResponseSchema = z.object({ message: z.string() });
const verificationResponseSchema = messageResponseSchema.extend({
  verified: z.boolean(),
  user: userSchema.nullable().optional(),
  delivery_mode: z.enum(["external", "development", "unavailable"]).nullable().optional(),
});
const verificationAuthResponseSchema = authResponseSchema.extend({
  verified: z.literal(true),
  message: z.string(),
});
const sessionSchema = z.object({
  id: z.string().uuid(),
  created_at: z.string(),
  last_used_at: z.string().nullable(),
  expires_at: z.string(),
  revoked_at: z.string().nullable(),
  client_label: z.string(),
  current: z.boolean(),
});
const sessionListSchema = z.object({ sessions: z.array(sessionSchema) });
const sessionMutationSchema = z.object({
  revoked_count: z.number().int().nonnegative(),
  current_session_preserved: z.boolean(),
});

export type AuthSession = z.infer<typeof sessionSchema>;
export type VerificationResponse = z.infer<typeof verificationResponseSchema>;
export type VerificationAuthResponse = z.infer<typeof verificationAuthResponseSchema>;

export async function register(email: string, password: string): Promise<AuthResponse> {
  return credentialsRequest("/api/v1/auth/register", email, password);
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  return credentialsRequest("/api/v1/auth/login", email, password);
}

export async function loadCurrentUser(): Promise<AuthUser> {
  return requestJson("/api/v1/auth/me", userSchema);
}

export async function resendVerification(): Promise<VerificationResponse> {
  return authenticatedJson(
    "/api/v1/auth/resend-verification",
    verificationResponseSchema,
    { method: "POST" },
  );
}

export async function verifyEmail(token: string): Promise<VerificationAuthResponse> {
  const result = await authenticatedJson(
    "/api/v1/auth/verify-email",
    verificationAuthResponseSchema,
    { method: "POST", body: JSON.stringify({ token }) },
  );
  setAccessToken(result.access_token);
  return result;
}

export async function completeOnboarding(displayName: string): Promise<AuthUser> {
  return authenticatedJson("/api/v1/auth/onboarding", userSchema, {
    method: "POST",
    body: JSON.stringify({ display_name: displayName }),
  });
}

export async function forgotPassword(email: string): Promise<string> {
  const result = await publicJson(
    "/api/v1/auth/forgot-password",
    messageResponseSchema,
    { email },
  );
  return result.message;
}

export async function resetPassword(token: string, newPassword: string): Promise<string> {
  const result = await publicJson(
    "/api/v1/auth/reset-password",
    messageResponseSchema,
    { token, new_password: newPassword },
  );
  return result.message;
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<AuthResponse> {
  const result = await authenticatedJson(
    "/api/v1/auth/change-password",
    authResponseSchema,
    {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    },
  );
  setAccessToken(result.access_token);
  return result;
}

export async function listSessions(): Promise<AuthSession[]> {
  const result = await requestJson("/api/v1/auth/sessions", sessionListSchema);
  return result.sessions;
}

export async function revokeSession(sessionId: string): Promise<boolean> {
  const result = await authenticatedJson(
    `/api/v1/auth/sessions/${encodeURIComponent(sessionId)}`,
    sessionMutationSchema,
    { method: "DELETE" },
  );
  if (!result.current_session_preserved) {
    setAccessToken(null);
  }
  return result.current_session_preserved;
}

export async function revokeAllSessions(
  preserveCurrentSession: boolean,
): Promise<number> {
  const result = await authenticatedJson(
    "/api/v1/auth/sessions/revoke-all",
    sessionMutationSchema,
    {
      method: "POST",
      body: JSON.stringify({ preserve_current_session: preserveCurrentSession }),
    },
  );
  if (!result.current_session_preserved) {
    setAccessToken(null);
  }
  return result.revoked_count;
}

export async function restoreSession(): Promise<AuthUser> {
  await refreshAccessToken();
  return loadCurrentUser();
}

export async function logout(): Promise<void> {
  try {
    const response = await fetch(toApiUrl("/api/v1/auth/logout"), {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw await apiErrorFromResponse(response);
    }
  } finally {
    setAccessToken(null);
  }
}

async function credentialsRequest(
  path: string,
  email: string,
  password: string,
): Promise<AuthResponse> {
  const response = await fetch(toApiUrl(path), {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  const parsed = authResponseSchema.parse(await response.json());
  setAccessToken(parsed.access_token);
  return parsed;
}

async function publicJson<T>(
  path: string,
  schema: z.ZodType<T>,
  body: unknown,
): Promise<T> {
  const response = await fetch(toApiUrl(path), {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  return schema.parse(await response.json());
}

async function authenticatedJson<T>(
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit,
): Promise<T> {
  const response = await authenticatedFetch(toApiUrl(path), {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  return schema.parse(await response.json());
}
