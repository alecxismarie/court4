"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
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
  AUTH_SESSION_INVALID_EVENT,
  EMAIL_VERIFICATION_REQUIRED_EVENT,
  isDefinitiveAuthenticationFailure,
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

  const resetAuthenticatedState = useCallback(() => {
    setAccessToken(null);
    setUser((currentUser) => {
      if (currentUser) {
        clearPlayerOnboardingPending(currentUser.id);
        clearFirstPlayerWelcome(currentUser.id);
      }
      return null;
    });
  }, []);

  useEffect(() => {
    let active = true;
    restoreSession()
      .then((currentUser) => {
        if (currentUser.display_name) clearPlayerOnboardingPending(currentUser.id);
        if (active) setUser(currentUser);
      })
      .catch((error) => {
        if (active && isDefinitiveAuthenticationFailure(error)) {
          resetAuthenticatedState();
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [resetAuthenticatedState]);

  useEffect(() => {
    const redirectToActivation = () => router.replace("/verification-pending");
    const resetInvalidSession = () => resetAuthenticatedState();
    window.addEventListener(EMAIL_VERIFICATION_REQUIRED_EVENT, redirectToActivation);
    window.addEventListener(AUTH_SESSION_INVALID_EVENT, resetInvalidSession);
    return () => {
      window.removeEventListener(EMAIL_VERIFICATION_REQUIRED_EVENT, redirectToActivation);
      window.removeEventListener(AUTH_SESSION_INVALID_EVENT, resetInvalidSession);
    };
  }, [resetAuthenticatedState, router]);

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
        try {
          const currentUser = await restoreSession();
          setUser(currentUser);
          return currentUser;
        } catch (error) {
          if (isDefinitiveAuthenticationFailure(error)) {
            resetAuthenticatedState();
          }
          throw error;
        }
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
        try {
          await logoutRequest();
        } finally {
          resetAuthenticatedState();
        }
      },
    }),
    [loading, resetAuthenticatedState, user],
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
