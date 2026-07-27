import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CalibrationReadinessDashboard } from "@/components/calibration-readiness-dashboard";
import type { CalibrationReadinessSummary } from "@/lib/api/calibration-readiness";
import { getCalibrationReadiness } from "@/lib/api/calibration-readiness";
import { renderWithQueryClient } from "@/test/render";

vi.mock("@/lib/api/calibration-readiness", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/calibration-readiness")>();
  return { ...actual, getCalibrationReadiness: vi.fn() };
});

const mockedGetReadiness = vi.mocked(getCalibrationReadiness);

describe("calibration readiness dashboard", () => {
  beforeEach(() => {
    mockedGetReadiness.mockResolvedValue(readinessFixture());
  });

  it("shows evidence gaps without presenting unreviewed values as zero rates", async () => {
    renderWithQueryClient(<CalibrationReadinessDashboard />);

    expect(await screen.findByRole("heading", { name: "Calibration readiness" })).toBeInTheDocument();
    expect(screen.getByText("COLLECTING EVIDENCE")).toBeInTheDocument();
    expect(screen.getByText("Holdout").nextElementSibling).toHaveTextContent("0");
    expect(screen.getAllByText("Not reviewed")).toHaveLength(5);
    expect(screen.getByText(/Shadow estimates only/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("makes stale source data explicit", async () => {
    const fixture = readinessFixture();
    mockedGetReadiness.mockResolvedValue({
      ...fixture,
      source_status: {
        ...fixture.source_status,
        report: "STALE",
        overall: "STALE",
        messages: ["The calibration report does not match the current manifest."],
      },
      readiness: {
        ...fixture.readiness,
        verdict: "NOT_READY",
        explanation: "Readiness cannot be assessed from stale source data.",
      },
    });

    renderWithQueryClient(<CalibrationReadinessDashboard />);

    expect(await screen.findByText("NOT READY")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("STALE source data");
    expect(screen.getByRole("alert")).toHaveTextContent("does not match");
  });
});

function readinessFixture(): CalibrationReadinessSummary {
  const unreviewedMetric = (key: string, label: string) => ({
    key,
    label,
    numerator: 0,
    denominator: 0,
    percentage: null,
    raw_count: 0,
    availability: "NOT_REVIEWED" as const,
    note: "No reviewed denominator.",
  });
  return {
    schema_version: 1,
    internal_only: true,
    read_only: true,
    source_status: {
      manifest: "CURRENT",
      report: "CURRENT",
      integrity: "CURRENT",
      governance: "CURRENT",
      overall: "CURRENT",
      messages: [],
    },
    dataset: {
      total_samples: 2,
      development_count: 1,
      validation_count: 1,
      holdout_count: 0,
      reviewed_samples: 0,
      partially_reviewed_samples: 2,
      unreviewed_samples: 0,
      last_evaluation_timestamp: "2026-07-27T00:00:00Z",
      manifest_schema_version: 2,
      manifest_version: "2.0.0",
      report_schema_version: 2,
    },
    balance: {
      categories: [
        {
          category: "orientation",
          counts: { landscape: 1, vertical: 1 },
          represented: ["landscape", "vertical"],
          missing: [],
          underrepresented: ["landscape", "vertical"],
        },
      ],
      warnings: ["The dataset is too small for broad accuracy claims."],
    },
    artifact_readiness: [
      { readiness: "LEGACY_COMPATIBLE", count: 2, sample_ids: ["landscape", "vertical"] },
    ],
    review_completion: [
      {
        key: "active_play",
        label: "Active Play intervals",
        reviewed_samples: 0,
        total_samples: 2,
        reviewed_items: 0,
        reviewed_seconds: 0,
        availability: "NOT_REVIEWED",
      },
    ],
    calibration_outcomes: [],
    active_play: {
      shadow_mode: true,
      policy_version: "active-play-v1",
      generated_intervals: 18,
      reviewed_intervals: 0,
      reviewed_duration_seconds: 0,
      likely_active_seconds: 0,
      likely_idle_seconds: 0,
      unknown_seconds: 30,
      false_active: unreviewedMetric("false_active", "False active"),
      false_idle: unreviewedMetric("false_idle", "False idle"),
      boundary_error: unreviewedMetric("boundary_error", "Boundary error"),
      abstention_rate: unreviewedMetric("abstention", "Abstention rate"),
      coverage_rate: unreviewedMetric("coverage", "Coverage rate"),
      current_schema_sample_count: 0,
      stale_artifact_sample_count: 2,
    },
    disagreements: [],
    unresolved_items: [],
    policy_safety: {
      recording_policy_version: "recording-quality-v1",
      active_play_policy_version: "active-play-v1",
      readiness_policy_version: "calibration-readiness-v1",
      recording_policy_immutable: true,
      active_play_policy_immutable: true,
      policies_frozen_for_review: false,
      threshold_simulations_exist: false,
      holdout_protection_enabled: true,
      production_thresholds_unchanged: true,
      reviewer_labels_unchanged: true,
      deterministic_report_status: "MATCH",
      calibration_report_sha256: "a".repeat(64),
      false_active_budget_approved: false,
      false_idle_budget_approved: false,
    },
    readiness: {
      verdict: "COLLECTING_EVIDENCE",
      explanation: "Court4 is collecting calibration evidence.",
      reasons: ["Current sources loaded."],
      blockers: ["No holdout sample exists."],
      warnings: ["Rates remain provisional."],
      satisfied_criteria: ["Thresholds were not changed."],
      recommended_actions: ["Add a holdout sample."],
      policy_version: "calibration-readiness-v1",
    },
  };
}
