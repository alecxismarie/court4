"use client";

import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  completeOnboarding as completeOnboardingRequest,
  type AuthUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  restoreSession,
  verifyEmail as verifyEmailRequest,
} from "@/lib/api/auth";
import {
  EMAIL_VERIFICATION_REQUIRED_EVENT,
  setAccessToken,
} from "@/lib/api/client";
import {
  clearPlayerOnboardingPending,
  clearFirstPlayerWelcome,
  markPlayerOnboardingPending,
} from "@/lib/profile-onboarding";

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (email: string, password: string) => Promise<AuthUser>;
  refreshUser: () => Promise<AuthUser>;
  verifyEmail: (token: string) => Promise<string>;
  completeOnboarding: (displayName: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    restoreSession()
      .then((currentUser) => {
        if (currentUser.display_name) clearPlayerOnboardingPending(currentUser.id);
        if (active) setUser(currentUser);
      })
      .catch(() => {
        setAccessToken(null);
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const redirectToActivation = () => router.replace("/verification-pending");
    window.addEventListener(EMAIL_VERIFICATION_REQUIRED_EVENT, redirectToActivation);
    return () => {
      window.removeEventListener(EMAIL_VERIFICATION_REQUIRED_EVENT, redirectToActivation);
    };
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      login: async (email, password) => {
        const result = await loginRequest(email, password);
        clearFirstPlayerWelcome(result.user.id);
        if (result.user.display_name) clearPlayerOnboardingPending(result.user.id);
        setUser(result.user);
        return result.user;
      },
      register: async (email, password) => {
        const result = await registerRequest(email, password);
        markPlayerOnboardingPending(result.user.id);
        setUser(result.user);
        return result.user;
      },
      refreshUser: async () => {
        const currentUser = await restoreSession();
        setUser(currentUser);
        return currentUser;
      },
      verifyEmail: async (token) => {
        const result = await verifyEmailRequest(token);
        if (result.user.display_name) {
          clearPlayerOnboardingPending(result.user.id);
        } else {
          markPlayerOnboardingPending(result.user.id);
        }
        setUser(result.user);
        return result.message;
      },
      completeOnboarding: async (displayName) => {
        const completedUser = await completeOnboardingRequest(displayName);
        clearPlayerOnboardingPending(completedUser.id);
        clearFirstPlayerWelcome(completedUser.id);
        setUser(completedUser);
        return completedUser;
      },
      logout: async () => {
        await logoutRequest();
        if (user) clearFirstPlayerWelcome(user.id);
        setUser(null);
      },
    }),
    [loading, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}

export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
}
