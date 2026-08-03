"use client";

import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

import {
  type AuthUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  restoreSession,
} from "@/lib/api/auth";
import { setAccessToken } from "@/lib/api/client";
import {
  clearFirstPlayerWelcome,
  markPlayerOnboardingPending,
} from "@/lib/profile-onboarding";

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  refreshUser: () => Promise<AuthUser>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    restoreSession()
      .then((currentUser) => {
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

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      login: async (email, password) => {
        const result = await loginRequest(email, password);
        clearFirstPlayerWelcome(result.user.id);
        setUser(result.user);
      },
      register: async (email, password) => {
        const result = await registerRequest(email, password);
        markPlayerOnboardingPending(result.user.id);
        setUser(result.user);
      },
      refreshUser: async () => {
        const currentUser = await restoreSession();
        setUser(currentUser);
        return currentUser;
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
