"use client";

import {
  ArrowRight,
  ChartNoAxesCombined,
  CircleCheck,
  FileText,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";
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
  const showFirstAnalysisState =
    !analyses.isLoading &&
    !playHistory.isLoading &&
    !latestCompleted &&
    !latestInsight;

  useEffect(() => {
    setFirstWelcome(
      auth?.user
        ? auth.user.last_login_at === null || isFirstPlayerWelcome(auth.user.id)
        : false,
    );
  }, [auth?.user]);

  return (
    <div className="space-y-5 md:space-y-6">
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
      <section className="relative overflow-hidden rounded-2xl border border-court-navy/10 bg-gradient-to-br from-court-navy via-[#123e39] to-court-green p-5 shadow-[0_18px_45px_rgba(6,31,56,0.20)] md:overflow-visible md:rounded-md md:border-court-line md:bg-none md:bg-white md:p-6 md:shadow-panel">
        <div aria-hidden="true" className="absolute -right-16 -top-20 h-56 w-56 rounded-full border-[36px] border-white/5 md:hidden" />
        <div aria-hidden="true" className="absolute -bottom-20 right-20 h-40 w-40 rounded-full bg-court-lime/10 blur-2xl md:hidden" />
        <div className="relative flex items-center gap-4 md:gap-5">
          <Link
            href="/player"
            aria-label="Open player profile"
            title="Player profile"
            className="shrink-0 rounded-full outline-none ring-court-green transition hover:scale-105 focus-visible:ring-2 focus-visible:ring-offset-2"
          >
            <ProfileAvatar
              profile={profile}
              className="h-16 w-16 border-[3px] bg-white text-lg shadow-[0_10px_28px_rgba(0,0,0,0.22)] md:h-24 md:w-24 md:border-2 md:bg-court-panel md:text-2xl md:shadow-panel"
            />
          </Link>
          <div className="min-w-0">
            <p className="mb-1.5 text-[0.6875rem] font-bold uppercase tracking-[0.18em] text-court-lime md:hidden">
              Player dashboard
            </p>
            <h1 className="text-2xl font-semibold leading-tight text-white md:text-4xl md:text-court-ink">
              {displayName
                ? firstWelcome
                  ? `Welcome, ${displayName}`
                  : `Welcome back, ${displayName}!`
                : firstWelcome
                  ? "Welcome"
                  : "Welcome back!"}
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-5 text-white/75 md:mt-3 md:leading-6 md:text-court-muted">
              {firstWelcome
                ? "Start uploading your matches and see how your game is developing over time."
                : "Review your latest report and see how your game is developing over time."}
            </p>
          </div>
        </div>
      </section>

      <dl className="grid grid-cols-2 gap-3 md:gap-4 xl:grid-cols-4">
        <MetricCard
          label="Total reports"
          value={analyses.isLoading ? "Loading" : String(analyses.data?.total ?? 0)}
          icon={FileText}
        />
        <MetricCard
          label="Completed reports"
          value={analyses.isLoading ? "Loading" : String(completedCount)}
          icon={CircleCheck}
        />
        <MetricCard
          label="Qualified analyses"
          value={playHistory.isLoading ? "Loading" : String(playHistory.data?.eligible_count ?? 0)}
          icon={ShieldCheck}
        />
        <MetricCard
          label="Progress check"
          value={progressLabel(playHistory.data?.progress.status)}
          icon={ChartNoAxesCombined}
        />
      </dl>

      {showFirstAnalysisState ? (
        <section className="relative overflow-hidden rounded-2xl border border-court-line bg-white p-5 shadow-panel md:hidden">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex gap-4">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-court-lime/20 text-court-green">
                <Sparkles aria-hidden="true" className="h-6 w-6" />
              </span>
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-court-green">
                  Ready when you are
                </p>
                <h2 className="mt-1.5 text-xl font-semibold text-court-ink">
                  Your first analysis starts here
                </h2>
                <p className="mt-2 max-w-xl text-sm leading-6 text-court-muted">
                  Upload a clear match video to create your first report and begin
                  building your progress history.
                </p>
              </div>
            </div>
            <ButtonLink href="/upload-match" className="min-h-11 w-full shrink-0">
              <Upload aria-hidden="true" className="h-4 w-4" />
              Upload a match
            </ButtonLink>
          </div>
        </section>
      ) : null}

      <section
        className={`gap-4 lg:grid-cols-2 ${showFirstAnalysisState ? "hidden md:grid" : "grid"}`}
      >
          <article className="rounded-xl border border-court-line bg-white p-5 shadow-panel md:rounded-md">
            <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
              Latest completed analysis
            </p>
            {latestCompleted ? (
              <>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <h2 className="text-xl font-semibold text-court-ink">
                    {latestCompleted.title}
                  </h2>
                  <AnalysisStatusBadge status={latestCompleted.status} />
                </div>
                <p className="mt-2 text-sm text-court-muted">
                  {formatDateTime(latestCompleted.created_at)}
                </p>
                <p className="mt-3 text-sm leading-6 text-court-muted">
                  {latestCompleted.limitation ?? "Your report is ready to review."}
                </p>
                <ButtonLink
                  href={latestCompleted.report_url}
                  variant="secondary"
                  className="mt-4"
                >
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

          <article className="rounded-xl border border-court-line bg-white p-5 shadow-panel md:rounded-md">
            <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
              Latest verified movement insight
            </p>
            {latestInsight ? (
              <>
                <h2 className="mt-3 text-xl font-semibold text-court-ink">
                  {latestInsight.title}
                </h2>
                <p className="mt-3 text-sm leading-6 text-court-muted">
                  {latestInsight.summary}
                </p>
                <ButtonLink
                  href={latestInsight.report_url}
                  variant="secondary"
                  className="mt-4"
                >
                  View verified analysis
                  <ArrowRight aria-hidden="true" className="h-4 w-4" />
                </ButtonLink>
              </>
            ) : (
              <p className="mt-4 text-sm leading-6 text-court-muted">
                No verified movement insight is available from an evidence-qualified
                analysis yet.
              </p>
            )}
          </article>
      </section>

      <section className="rounded-2xl border border-court-line bg-white p-5 shadow-panel md:rounded-md">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-xs font-bold uppercase tracking-[0.16em] text-court-green md:text-xl md:font-semibold md:normal-case md:tracking-normal md:text-court-ink">
            Your progress
          </h2>
          <span className="rounded-full bg-court-panel px-3 py-1 text-xs font-semibold text-court-muted md:hidden">
            {progressLabel(playHistory.data?.progress.status)}
          </span>
        </div>
        <p className="mt-3 text-xl font-semibold leading-snug text-court-ink md:text-lg md:leading-7">
          {playHistory.data?.progress.answer ?? "Building your baseline"}
        </p>
        <p className="mt-2 text-sm leading-6 text-court-muted">
          {playHistory.data?.progress.explanation ??
            "Court4 will compare your earlier and recent qualified reports when enough data is available."}
        </p>
        {playHistory.data?.progress ? (
          <p
            className={`mt-3 text-xs leading-5 text-court-muted ${
              playHistory.data.progress.qualified_analysis_count === 0
                ? "hidden md:block"
                : ""
            }`}
          >
            {dashboardEvidenceContext(playHistory.data.progress)}
            {playHistory.data.progress.provisional ? " Provisional." : ""}
          </p>
        ) : null}
      </section>

      <section
        aria-label="Dashboard actions"
        className={`grid-cols-2 gap-3 md:flex md:flex-wrap ${
          showFirstAnalysisState ? "hidden md:flex" : "grid"
        }`}
      >
        <ButtonLink
          href="/analysis-history"
          variant="secondary"
          className="order-2 min-h-11 w-full md:order-none md:min-h-0 md:w-auto"
        >
          View Analysis History
        </ButtonLink>
        <ButtonLink
          href="/my-progress"
          variant="secondary"
          className="order-3 min-h-11 w-full md:order-none md:min-h-0 md:w-auto"
        >
          View progress
        </ButtonLink>
        <ButtonLink
          href="/upload-match"
          className="order-1 col-span-2 min-h-12 w-full md:order-none md:min-h-0 md:w-auto"
        >
          <Upload aria-hidden="true" className="h-4 w-4 md:hidden" />
          Upload Match
        </ButtonLink>
      </section>
    </div>
  );
}

function MetricCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: typeof FileText;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-court-line bg-white p-3.5 shadow-panel md:rounded-md md:p-4">
      <div className="flex items-start justify-between gap-2">
        <dt className="text-[0.6875rem] font-bold uppercase leading-4 tracking-[0.08em] text-court-muted md:text-xs md:font-semibold md:tracking-wide">
          {label}
        </dt>
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-court-panel text-court-green md:hidden">
          <Icon aria-hidden="true" className="h-3.5 w-3.5" />
        </span>
      </div>
      <dd className="mt-2 break-words text-xl font-semibold leading-tight text-court-ink md:text-2xl md:leading-8">
        {value}
      </dd>
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
