"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AnalysisStatusBadge } from "@/components/history-badges";
import { ProfileAvatar } from "@/components/profile-avatar";
import { ButtonLink } from "@/components/ui/button";
import { FirstTimeProfileModal } from "@/components/first-time-profile-modal";
import { useOptionalAuth } from "@/lib/auth-context";
import { useAnalysisHistory, usePlayHistory } from "@/lib/use-history";
import { usePlayerProfile } from "@/lib/use-player-profile";
import { isFirstPlayerWelcome } from "@/lib/profile-onboarding";
import { formatDateTime } from "@/lib/utils";
import { formatTrackedTime } from "@/lib/workspace-data";

export function DashboardWorkspace() {
  const auth = useOptionalAuth();
  const { profile, isLoaded, save } = usePlayerProfile();
  const [firstWelcome, setFirstWelcome] = useState(false);
  const analyses = useAnalysisHistory();
  const playHistory = usePlayHistory();
  const displayName = profile.displayName;
  const latestCompleted = analyses.data?.items.find((item) =>
    ["READY", "LIMITED", "UNSUITABLE"].includes(item.status),
  );
  const latestInsight = playHistory.data?.latest_verified_match_iq[0];
  const completedCount =
    analyses.data?.items.filter((item) =>
      ["READY", "LIMITED", "UNSUITABLE"].includes(item.status),
    ).length ?? 0;

  useEffect(() => {
    setFirstWelcome(
      auth?.user
        ? auth.user.last_login_at === null || isFirstPlayerWelcome(auth.user.id)
        : false,
    );
  }, [auth?.user]);

  return (
    <div className="space-y-6">
      <FirstTimeProfileModal
        userId={auth?.user?.id ?? null}
        profile={profile}
        isProfileLoaded={isLoaded}
        onboardingRequired={auth?.user?.display_name === null}
        saveProfile={save}
        completeOnboarding={async (displayName) => {
          if (!auth) throw new Error("A signed-in account is required to complete onboarding.");
          await auth.completeOnboarding(displayName);
        }}
        onComplete={() => setFirstWelcome(true)}
      />
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <div className="flex items-center gap-4 sm:gap-5">
          <Link
            href="/player"
            aria-label="Open player profile"
            title="Player profile"
            className="shrink-0 rounded-full outline-none ring-court-green transition hover:scale-105 focus-visible:ring-2 focus-visible:ring-offset-2"
          >
            <ProfileAvatar
              profile={profile}
              className="h-20 w-20 text-xl shadow-panel sm:h-24 sm:w-24 sm:text-2xl"
            />
          </Link>
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-court-ink md:text-4xl">
              {displayName
                ? firstWelcome
                  ? `Welcome, ${displayName}`
                  : `Welcome back, ${displayName}!`
                : firstWelcome
                  ? "Welcome"
                  : "Welcome back!"}
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-court-muted">
              {firstWelcome
                ? "Start uploading your matches and see how your game is developing over time."
                : "Review your latest report and see how your game is developing over time."}
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total reports"
          value={analyses.isLoading ? "Loading" : String(analyses.data?.total ?? 0)}
        />
        <MetricCard
          label="Completed reports"
          value={analyses.isLoading ? "Loading" : String(completedCount)}
        />
        <MetricCard
          label="Qualified analyses"
          value={playHistory.isLoading ? "Loading" : String(playHistory.data?.eligible_count ?? 0)}
        />
        <MetricCard
          label="Progress check"
          value={progressLabel(playHistory.data?.progress.status)}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <article className="rounded-md border border-court-line bg-white p-5 shadow-panel">
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            Latest completed analysis
          </p>
          {latestCompleted ? (
            <>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-semibold text-court-ink">{latestCompleted.title}</h2>
                <AnalysisStatusBadge status={latestCompleted.status} />
              </div>
              <p className="mt-2 text-sm text-court-muted">
                {formatDateTime(latestCompleted.created_at)}
              </p>
              <p className="mt-3 text-sm leading-6 text-court-muted">
                {latestCompleted.limitation ?? "Your report is ready to review."}
              </p>
              <ButtonLink href={latestCompleted.report_url} variant="secondary" className="mt-4">
                Open latest analysis
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
              </ButtonLink>
            </>
          ) : (
            <p className="mt-4 text-sm leading-6 text-court-muted">
              No completed analysis is available yet.
            </p>
          )}
        </article>

        <article className="rounded-md border border-court-line bg-white p-5 shadow-panel">
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            Latest verified movement insight
          </p>
          {latestInsight ? (
            <>
              <h2 className="mt-3 text-xl font-semibold text-court-ink">{latestInsight.title}</h2>
              <p className="mt-3 text-sm leading-6 text-court-muted">{latestInsight.summary}</p>
              <ButtonLink href={latestInsight.report_url} variant="secondary" className="mt-4">
                View verified analysis
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
              </ButtonLink>
            </>
          ) : (
            <p className="mt-4 text-sm leading-6 text-court-muted">
              No verified movement insight is available from an evidence-qualified analysis yet.
            </p>
          )}
        </article>
      </section>

      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <h2 className="text-xl font-semibold text-court-ink">Your progress</h2>
        <p className="mt-3 text-lg font-semibold text-court-ink">
          {playHistory.data?.progress.answer ?? "Building your baseline"}
        </p>
        <p className="mt-2 text-sm leading-6 text-court-muted">
          {playHistory.data?.progress.explanation ??
            "Court4 will compare your earlier and recent qualified reports when enough data is available."}
        </p>
        {playHistory.data?.progress ? (
          <p className="mt-3 text-xs leading-5 text-court-muted">
            {dashboardEvidenceContext(playHistory.data.progress)}
            {playHistory.data.progress.provisional ? " Provisional." : ""}
          </p>
        ) : null}
      </section>

      <section className="flex flex-wrap gap-3">
        <ButtonLink href="/analysis-history" variant="secondary">
          View Analysis History
        </ButtonLink>
        <ButtonLink href="/my-progress" variant="secondary">
          View progress
        </ButtonLink>
        <ButtonLink href="/upload-match">Upload Match</ButtonLink>
      </section>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-court-line bg-white p-4 shadow-panel">
      <dt className="text-xs font-semibold uppercase tracking-wide text-court-muted">{label}</dt>
      <dd className="mt-2 break-words text-2xl font-semibold text-court-ink">{value}</dd>
    </div>
  );
}

function progressLabel(status: string | undefined): string {
  if (!status) return "Loading";
  if (status === "NO_QUALIFIED_REPORTS") return "Waiting for evidence";
  if (status === "BUILDING_BASELINE") return "Building baseline";
  if (status === "BASELINE_ESTABLISHED") return "Baseline ready";
  if (status === "MIXED_OR_INCOMPATIBLE_REPORTS") return "Not comparable yet";
  return "Comparison ready";
}

function dashboardEvidenceContext(
  progress: NonNullable<ReturnType<typeof usePlayHistory>["data"]>["progress"],
): string {
  const period =
    progress.comparison_period_start && progress.comparison_period_end
      ? ` from ${formatDashboardDate(progress.comparison_period_start)}–${formatDashboardDate(
          progress.comparison_period_end,
        )}`
      : "";
  return `Based on ${progress.qualified_analysis_count} qualified ${
    progress.qualified_analysis_count === 1 ? "analysis" : "analyses"
  }${period}, covering ${formatTrackedTime(
    progress.qualified_observation_seconds,
  )} of reliable observation.`;
}

function formatDashboardDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}
