"use client";

import { Save } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import {
  dominantHandOptions,
  emptyPlayerProfile,
  experienceLevelOptions,
  formatDominantHand,
  formatExperienceLevel,
  normalizePlayerProfile,
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
    setStatus(null);
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
    setStatus("Player profile saved in this browser.");
  }

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Your details
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-court-ink">Player profile</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-court-muted">
          Choose the details Court4 should use for you. They are saved only in this
          browser—not to an account—and won&apos;t sync to other devices.
        </p>
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <form
          onSubmit={submit}
          className="rounded-md border border-court-line bg-white p-5 shadow-panel"
          aria-label="Player profile form"
        >
          <div className="grid gap-4">
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
              Save Player Profile
            </Button>
            {status ? (
              <p className="text-sm font-medium text-court-green" role="status">
                {status}
              </p>
            ) : null}
          </div>
        </form>

        <aside className="rounded-md border border-court-line bg-white p-5 shadow-panel">
          <h2 className="text-lg font-semibold text-court-ink">Profile preview</h2>
          <dl className="mt-4 grid gap-3 text-sm">
            <PreviewItem label="Display name" value={form.displayName || "Not set"} />
            <PreviewItem label="Dominant hand" value={formatDominantHand(form.dominantHand)} />
            <PreviewItem
              label="Experience"
              value={formatExperienceLevel(form.experienceLevel)}
            />
            <PreviewItem label="Home club or location" value={form.homeClub || "Not set"} />
          </dl>
          <p className="mt-5 text-xs leading-5 text-court-muted">
            Profile data is stored in browser local storage. Court4 does not make
            this profile public.
          </p>
        </aside>
      </section>
    </div>
  );
}

function PreviewItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-court-line bg-court-panel p-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-court-muted">{label}</dt>
      <dd className="mt-1 break-words font-semibold text-court-ink">{value}</dd>
    </div>
  );
}

function FormError({ message }: { message: string }) {
  return <span className="text-xs font-semibold text-court-red">{message}</span>;
}
