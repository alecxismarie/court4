"use client";

import { useEffect, useState } from "react";

import {
  emptyPlayerProfile,
  getPlayerProfile,
  PLAYER_PROFILE_UPDATED_EVENT,
  savePlayerProfile,
  type PlayerProfile,
} from "@/lib/player-profile";

export function usePlayerProfile() {
  const [profile, setProfile] = useState<PlayerProfile>(emptyPlayerProfile);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    const loadProfile = () => {
      setProfile(getPlayerProfile());
      setIsLoaded(true);
    };

    loadProfile();
    window.addEventListener(PLAYER_PROFILE_UPDATED_EVENT, loadProfile);
    window.addEventListener("storage", loadProfile);
    return () => {
      window.removeEventListener(PLAYER_PROFILE_UPDATED_EVENT, loadProfile);
      window.removeEventListener("storage", loadProfile);
    };
  }, []);

  const save = (nextProfile: PlayerProfile) => {
    const saved = savePlayerProfile(nextProfile);
    setProfile(saved);
    return saved;
  };

  return { profile, isLoaded, save };
}
