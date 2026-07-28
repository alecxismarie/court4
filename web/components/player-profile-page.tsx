"use client";

import { Camera, Save, Trash2 } from "lucide-react";
import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";

import { ProfileAvatar } from "@/components/profile-avatar";
import {
  dominantHandOptions,
  emptyPlayerProfile,
  experienceLevelOptions,
  formatDominantHand,
  formatExperienceLevel,
  normalizePlayerProfile,
  PROFILE_IMAGE_ACCEPT,
  readProfileImageFile,
  validateProfileImageFile,
  validatePlayerProfile,
  type PlayerProfile,
  type PlayerProfileErrors,
} from "@/lib/player-profile";
import { usePlayerProfile } from "@/lib/use-player-profile";
import { Button } from "@/components/ui/button";

export function PlayerProfilePage() {
  const { profile, isLoaded, save } = usePlayerProfile();
  const [form, setForm] = useState<PlayerProfile>(emptyPlayerProfile);
  const [errors, setErrors] = useState<PlayerProfileErrors>({});
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (isLoaded) {
      setForm(profile);
    }
  }, [isLoaded, profile]);

  function updateField<TKey extends keyof PlayerProfile>(
    key: TKey,
    value: PlayerProfile[TKey],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    setStatus(null);
  }

  async function selectProfilePhoto(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file) {
      return;
    }
    const fileError = validateProfileImageFile(file);
    if (fileError) {
      setErrors((current) => ({ ...current, profileImageDataUrl: fileError }));
      return;
    }
    try {
      updateField("profileImageDataUrl", await readProfileImageFile(file));
    } catch {
      setErrors((current) => ({
        ...current,
        profileImageDataUrl: "Profile photo could not be read.",
      }));
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = normalizePlayerProfile(form);
    const nextErrors = validatePlayerProfile(normalized);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setStatus(null);
      return;
    }
    const saved = save(normalized);
    setForm(saved);
    setStatus("Profile saved.");
  }

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <h1 className="text-3xl font-semibold text-court-ink">Player profile</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-court-muted">
          Update the photo and details used across Court4.
        </p>
      </section>

      <section className="max-w-3xl">
        <form
          onSubmit={submit}
          className="rounded-md border border-court-line bg-white p-6 shadow-panel"
          aria-label="Player profile form"
        >
          <div className="grid gap-4">
            <div className="flex flex-wrap items-center gap-4 rounded-md border border-court-line bg-court-panel p-4">
              <ProfileAvatar profile={form} className="h-20 w-20 text-xl" />
              <div>
                <p className="text-sm font-semibold text-court-ink">Profile photo</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <label
                    htmlFor="profile-photo"
                    className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-md border border-court-line bg-white px-3 py-2 text-sm font-semibold text-court-ink hover:bg-court-panel"
                  >
                    <Camera aria-hidden="true" className="h-4 w-4" />
                    {form.profileImageDataUrl ? "Change photo" : "Choose photo"}
                  </label>
                  <input
                    id="profile-photo"
                    aria-label="Profile photo"
                    type="file"
                    accept={PROFILE_IMAGE_ACCEPT}
                    className="sr-only"
                    onChange={selectProfilePhoto}
                  />
                  {form.profileImageDataUrl ? (
                    <button
                      type="button"
                      onClick={() => updateField("profileImageDataUrl", "")}
                      className="inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-semibold text-court-muted hover:bg-white hover:text-court-ink"
                    >
                      <Trash2 aria-hidden="true" className="h-4 w-4" />
                      Remove photo
                    </button>
                  ) : null}
                </div>
                <p className="mt-2 text-xs font-medium text-court-muted">
                  JPG, PNG or WebP · Up to 10 MB
                </p>
                {errors.profileImageDataUrl ? (
                  <FormError message={errors.profileImageDataUrl} />
                ) : null}
              </div>
            </div>

            <label className="grid gap-2 text-sm font-semibold text-court-ink">
              Display name
              <input
                className="rounded-md border border-court-line px-3 py-2 text-sm"
                value={form.displayName}
                maxLength={37}
                onChange={(event) => updateField("displayName", event.target.value)}
              />
              <span className="text-xs font-medium text-court-muted">
                Used on the Dashboard and share-card defaults.
              </span>
              {errors.displayName ? <FormError message={errors.displayName} /> : null}
            </label>

            <label className="grid gap-2 text-sm font-semibold text-court-ink">
              Dominant hand
              <select
                className="rounded-md border border-court-line px-3 py-2 text-sm"
                value={form.dominantHand}
                onChange={(event) =>
                  updateField("dominantHand", event.target.value as PlayerProfile["dominantHand"])
                }
              >
                {dominantHandOptions.map((option) => (
                  <option key={option} value={option}>
                    {formatDominantHand(option)}
                  </option>
                ))}
              </select>
              {errors.dominantHand ? <FormError message={errors.dominantHand} /> : null}
            </label>

            <label className="grid gap-2 text-sm font-semibold text-court-ink">
              Experience level
              <select
                className="rounded-md border border-court-line px-3 py-2 text-sm"
                value={form.experienceLevel}
                onChange={(event) =>
                  updateField(
                    "experienceLevel",
                    event.target.value as PlayerProfile["experienceLevel"],
                  )
                }
              >
                {experienceLevelOptions.map((option) => (
                  <option key={option} value={option}>
                    {formatExperienceLevel(option)}
                  </option>
                ))}
              </select>
              {errors.experienceLevel ? <FormError message={errors.experienceLevel} /> : null}
            </label>

            <label className="grid gap-2 text-sm font-semibold text-court-ink">
              Home club or location
              <input
                className="rounded-md border border-court-line px-3 py-2 text-sm"
                value={form.homeClub}
                maxLength={81}
                onChange={(event) => updateField("homeClub", event.target.value)}
              />
              <span className="text-xs font-medium text-court-muted">
                Optional. Leave blank if you do not want to store it.
              </span>
              {errors.homeClub ? <FormError message={errors.homeClub} /> : null}
            </label>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button type="submit">
              <Save aria-hidden="true" className="h-4 w-4" />
              Save changes
            </Button>
            {status ? (
              <p className="text-sm font-medium text-court-green" role="status">
                {status}
              </p>
            ) : null}
          </div>
        </form>
      </section>
    </div>
  );
}

function FormError({ message }: { message: string }) {
  return <span className="text-xs font-semibold text-court-red">{message}</span>;
}
