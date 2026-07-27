"use client";

import { ArrowRight, Share2, Upload } from "lucide-react";

import { usePlayerProfile } from "@/lib/use-player-profile";
import { useWorkspaceAnalyses } from "@/lib/use-workspace-analyses";
import {
  formatDistanceFeet,
  formatTrackedTime,
  getDominantZone,
} from "@/lib/workspace-data";
import { formatDateTime } from "@/lib/utils";
import { EmptyState } from "@/components/empty-state";
import { RecentMatches } from "@/components/recent-matches";
import { ButtonLink } from "@/components/ui/button";

export function DashboardWorkspace() {
  const { profile } = usePlayerProfile();
  const { summary, isLoading, analysisIds } = useWorkspaceAnalyses();
  const displayName = profile.displayName;
  const latest = summary.latestMatchIq;
  const latestAnalytics = latest?.analytics?.analytics ?? null;
  const latestMatchIQ = latest?.analytics?.match_iq ?? null;
  const latestInsight = latestMatchIQ?.insights[0] ?? null;
  const dominantZone = latest ? getDominantZone(latest) : null;

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto] lg:items-center">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
              Player workspace
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-court-ink md:text-4xl">
              {displayName ? `Welcome back, ${displayName}` : "Welcome back"}
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-court-muted">
              Review your latest Match IQ or upload another match.
            </p>
          </div>
          <ButtonLink href="/matches/upload">
            <Upload aria-hidden="true" className="h-4 w-4" />
            Upload Match
          </ButtonLink>
        </div>
      </section>

      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
              Latest Match IQ
            </p>
            <h2 className="mt-2 text-xl font-semibold text-court-ink">
              {latest
                ? latestMatchIQ?.quality_gate === "NORMAL"
                  ? "Verified movement insight"
                  : latestMatchIQ?.quality_gate === "CAUTIOUS"
                    ? "Analysis under review"
                    : "Limited by video quality"
                : "No verified insight yet"}
            </h2>
          </div>
          {latest ? (
            <div className="flex flex-wrap gap-2">
              <ButtonLink href={`/matches/${latest.analysisId}/analytics`} variant="secondary">
                View full results
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
              </ButtonLink>
              <ButtonLink href={`/matches/${latest.analysisId}/analytics#share-card`}>
                <Share2 aria-hidden="true" className="h-4 w-4" />
                Share results
              </ButtonLink>
            </div>
          ) : null}
        </div>

        {isLoading && analysisIds.length > 0 ? (
          <p className="mt-4 text-sm text-court-muted">Loading your latest match data.</p>
        ) : latest && latestAnalytics && latestMatchIQ ? (
          <div className="mt-5 grid gap-5 lg:grid-cols-[1.3fr_1fr]">
            <div>
              <p className="text-sm text-court-muted">
                {formatDateTime(latestAnalytics.created_at)}
              </p>
              <p className="mt-3 text-base leading-7 text-court-muted">
                {latestMatchIQ.summary}
              </p>
              {latestInsight && latestMatchIQ.quality_gate !== "INSUFFICIENT_EVIDENCE" ? (
                <div className="mt-4 rounded-md border border-court-line bg-court-panel p-4">
                  <p className="text-sm font-semibold text-court-ink">{latestInsight.title}</p>
                  <p className="mt-1 text-sm leading-6 text-court-muted">
                    {latestInsight.observation || latestInsight.statement}
                  </p>
                </div>
              ) : null}
            </div>
            <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <MetricCard
                label="Total distance"
                value={formatDistanceFeet(latestAnalytics.distance.total_distance_feet)}
              />
              <MetricCard
                label="Dominant zone"
                value={
                  dominantZone
                    ? `${dominantZone.label} ${dominantZone.percentage.toFixed(1)}%`
                    : "Unavailable"
                }
              />
              <MetricCard
                label="Tracked time"
                value={formatTrackedTime(latestAnalytics.zone_occupancy.tracked_time_seconds)}
              />
            </dl>
          </div>
        ) : (
          <EmptyState
            className="mt-5"
            title="Your latest Match IQ will appear here after you analyze a match."
            description="Court4 only shows verified results from completed match analyses."
            action={<ButtonLink href="/matches/upload">Upload Match</ButtonLink>}
          />
        )}
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Matches analyzed" value={String(summary.completedMatchCount)} />
        <MetricCard
          label="Total tracked distance"
          value={formatDistanceFeet(summary.totalDistanceFeet)}
        />
        <MetricCard
          label="Total tracked time"
          value={formatTrackedTime(summary.totalTrackedSeconds)}
        />
        <MetricCard
          label="Completed Match IQ reports"
          value={String(summary.completedMatchIqCount)}
        />
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-court-ink">Recent matches</h2>
            <p className="text-sm text-court-muted">Your locally remembered match activity.</p>
          </div>
          <ButtonLink href="/matches" variant="secondary">
            View Matches
            <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </ButtonLink>
        </div>
        <RecentMatches compact limit={3} showHeading={false} />
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
