"use client";

import { useEffect, useState } from "react";

import { useOptionalAuth } from "@/lib/auth-context";
import {
  emptyPlayerProfile,
  getPlayerProfile,
  PLAYER_PROFILE_UPDATED_EVENT,
  savePlayerProfile,
  type PlayerProfile,
} from "@/lib/player-profile";

export function usePlayerProfile() {
  const auth = useOptionalAuth();
  const userId = auth?.user?.id ?? null;
  const [state, setState] = useState<{
    userId: string | null;
    profile: PlayerProfile;
    isLoaded: boolean;
  }>({ userId: null, profile: emptyPlayerProfile, isLoaded: false });
  const profile = state.userId === userId ? state.profile : emptyPlayerProfile;
  const isLoaded = state.userId === userId && state.isLoaded;

  useEffect(() => {
    const loadProfile = () => {
      setState({
        userId,
        profile: userId ? getPlayerProfile(userId) : emptyPlayerProfile,
        isLoaded: true,
      });
    };

    loadProfile();
    window.addEventListener(PLAYER_PROFILE_UPDATED_EVENT, loadProfile);
    window.addEventListener("storage", loadProfile);
    return () => {
      window.removeEventListener(PLAYER_PROFILE_UPDATED_EVENT, loadProfile);
      window.removeEventListener("storage", loadProfile);
    };
  }, [userId]);

  const save = (nextProfile: PlayerProfile) => {
    if (!userId) {
      throw new Error("A signed-in account is required to save a player profile.");
    }
    const saved = savePlayerProfile(userId, nextProfile);
    setState({ userId, profile: saved, isLoaded: true });
    return saved;
  };

  return { profile, isLoaded, save };
}
