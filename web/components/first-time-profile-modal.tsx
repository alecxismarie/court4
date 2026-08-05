"use client";

import { UserRound } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { normalizeApiError } from "@/lib/api/client";
import {
  normalizePlayerProfile,
  validatePlayerProfile,
  type PlayerProfile,
} from "@/lib/player-profile";
import {
  completePlayerOnboarding,
  isPlayerOnboardingPending,
} from "@/lib/profile-onboarding";

type FirstTimeProfileModalProps = {
  userId: string | null;
  profile: PlayerProfile;
  isProfileLoaded: boolean;
  onboardingRequired: boolean;
  saveProfile: (profile: PlayerProfile) => PlayerProfile;
  completeOnboarding: (displayName: string) => Promise<void>;
  onComplete?: () => void;
};

export function FirstTimeProfileModal({
  userId,
  profile,
  isProfileLoaded,
  onboardingRequired,
  saveProfile,
  completeOnboarding: completeOnboardingRequest,
  onComplete,
}: FirstTimeProfileModalProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const normalizedPreview = useMemo(
    () => normalizePlayerProfile({ ...profile, displayName: name }).displayName,
    [name, profile],
  );

  useEffect(() => {
    if (
      userId &&
      isProfileLoaded &&
      ((isPlayerOnboardingPending(userId) && !profile.displayName) || onboardingRequired)
    ) {
      setName("");
      setError(null);
      setOpen(true);
    }
  }, [isProfileLoaded, onboardingRequired, profile.displayName, userId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!userId) return;

    const nextProfile = normalizePlayerProfile({ ...profile, displayName: name });
    if (!nextProfile.displayName) {
      setError("Enter the name you would like Court4 to use.");
      return;
    }
    const validationError = validatePlayerProfile(nextProfile).displayName;
    if (validationError) {
      setError(validationError);
      return;
    }

    setSubmitting(true);
    try {
      await completeOnboardingRequest(nextProfile.displayName);
      saveProfile(nextProfile);
      completePlayerOnboarding(userId);
      onComplete?.();
      setOpen(false);
    } catch (caught) {
      setError(normalizeApiError(caught).message);
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-court-navy/70 px-4 py-8 backdrop-blur-sm">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="player-onboarding-title"
        aria-describedby="player-onboarding-description"
        className="w-full max-w-lg rounded-xl border border-court-line bg-white p-6 shadow-2xl sm:p-8"
      >
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-court-lime/20 text-court-green">
          <UserRound aria-hidden="true" className="h-7 w-7" />
        </div>
        <p className="mt-4 text-center text-xs font-bold uppercase tracking-[0.18em] text-court-green">
          Set up your player
        </p>
        <h2
          id="player-onboarding-title"
          className="mt-2 text-center text-3xl font-semibold text-court-ink"
        >
          {normalizedPreview ? `Welcome, ${normalizedPreview}!` : "What should we call you?"}
        </h2>
        <p
          id="player-onboarding-description"
          className="mx-auto mt-3 max-w-md text-center text-sm leading-6 text-court-muted"
        >
          Add the name you want to see across Court4. Then visit the Player section to
          finish your player information so we can know more about you and keep your
          progress organized.
        </p>

        <form className="mt-6" onSubmit={(event) => void submit(event)}>
          <label htmlFor="player-onboarding-name" className="grid gap-2 text-sm font-semibold text-court-ink">
            What should we call you?
            <input
              id="player-onboarding-name"
              autoFocus
              required
              maxLength={37}
              autoComplete="name"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setError(null);
              }}
              placeholder="Enter your name"
              className="rounded-md border border-court-line px-3 py-3 text-base font-normal outline-none ring-court-green focus:ring-2"
            />
          </label>
          {error ? (
            <p className="mt-2 text-sm font-semibold text-court-red" role="alert">
              {error}
            </p>
          ) : null}
          <p className="mt-3 text-xs leading-5 text-court-muted">
            You can update this name, add a profile photo, and complete the rest of your
            details anytime in the Player section.
          </p>
          <Button type="submit" className="mt-6 w-full" disabled={!name.trim() || submitting}>
            {submitting ? "Saving…" : "Done"}
          </Button>
        </form>
      </section>
    </div>
  );
}
