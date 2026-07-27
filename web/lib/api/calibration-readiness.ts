import { z } from "zod";

import { requestJson } from "@/lib/api/client";

const dataStatusSchema = z.enum(["CURRENT", "STALE", "MISSING", "INVALID"]);
const availabilitySchema = z.enum([
  "AVAILABLE",
  "PROVISIONAL",
  "NOT_REVIEWED",
  "NOT_AVAILABLE",
  "STALE",
]);

const metricSchema = z.object({
  key: z.string(),
  label: z.string(),
  numerator: z.number().nonnegative().nullable(),
  denominator: z.number().nonnegative().nullable(),
  percentage: z.number().min(0).max(100).nullable(),
  raw_count: z.number().int().nonnegative().nullable(),
  availability: availabilitySchema,
  note: z.string().nullable(),
});

export const calibrationReadinessSummarySchema = z.object({
  schema_version: z.literal(1),
  internal_only: z.literal(true),
  read_only: z.literal(true),
  source_status: z.object({
    manifest: dataStatusSchema,
    report: dataStatusSchema,
    integrity: dataStatusSchema,
    governance: dataStatusSchema,
    overall: dataStatusSchema,
    messages: z.array(z.string()),
  }),
  dataset: z.object({
    total_samples: z.number().int().nonnegative(),
    development_count: z.number().int().nonnegative(),
    validation_count: z.number().int().nonnegative(),
    holdout_count: z.number().int().nonnegative(),
    reviewed_samples: z.number().int().nonnegative(),
    partially_reviewed_samples: z.number().int().nonnegative(),
    unreviewed_samples: z.number().int().nonnegative(),
    last_evaluation_timestamp: z.string().datetime().nullable(),
    manifest_schema_version: z.number().int().positive().nullable(),
    manifest_version: z.string().nullable(),
    report_schema_version: z.number().int().positive().nullable(),
  }),
  balance: z.object({
    categories: z.array(
      z.object({
        category: z.string(),
        counts: z.record(z.number().int().nonnegative()),
        represented: z.array(z.string()),
        missing: z.array(z.string()),
        underrepresented: z.array(z.string()),
      }),
    ),
    warnings: z.array(z.string()),
  }),
  artifact_readiness: z.array(
    z.object({
      readiness: z.string(),
      count: z.number().int().nonnegative(),
      sample_ids: z.array(z.string()),
    }),
  ),
  review_completion: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
      reviewed_samples: z.number().int().nonnegative(),
      total_samples: z.number().int().nonnegative(),
      reviewed_items: z.number().int().nonnegative(),
      reviewed_seconds: z.number().nonnegative().nullable(),
      availability: availabilitySchema,
    }),
  ),
  calibration_outcomes: z.array(metricSchema),
  active_play: z.object({
    shadow_mode: z.literal(true),
    policy_version: z.string().nullable(),
    generated_intervals: z.number().int().nonnegative(),
    reviewed_intervals: z.number().int().nonnegative(),
    reviewed_duration_seconds: z.number().nonnegative(),
    likely_active_seconds: z.number().nonnegative(),
    likely_idle_seconds: z.number().nonnegative(),
    unknown_seconds: z.number().nonnegative(),
    false_active: metricSchema,
    false_idle: metricSchema,
    boundary_error: metricSchema,
    abstention_rate: metricSchema,
    coverage_rate: metricSchema,
    current_schema_sample_count: z.number().int().nonnegative(),
    stale_artifact_sample_count: z.number().int().nonnegative(),
  }),
  disagreements: z.array(
    z.object({
      category: z.string(),
      label: z.string(),
      count: z.number().int().nonnegative().nullable(),
      sample_ids: z.array(z.string()),
      availability: availabilitySchema,
    }),
  ),
  unresolved_items: z.array(
    z.object({
      sample_id: z.string(),
      category: z.string(),
      reason: z.string(),
    }),
  ),
  policy_safety: z.object({
    recording_policy_version: z.string(),
    active_play_policy_version: z.string(),
    readiness_policy_version: z.string(),
    recording_policy_immutable: z.boolean(),
    active_play_policy_immutable: z.boolean(),
    policies_frozen_for_review: z.boolean(),
    threshold_simulations_exist: z.boolean(),
    holdout_protection_enabled: z.boolean(),
    production_thresholds_unchanged: z.boolean().nullable(),
    reviewer_labels_unchanged: z.boolean().nullable(),
    deterministic_report_status: z.enum(["MATCH", "CHANGED", "NOT_VERIFIED"]),
    calibration_report_sha256: z.string().nullable(),
    false_active_budget_approved: z.boolean(),
    false_idle_budget_approved: z.boolean(),
  }),
  readiness: z.object({
    verdict: z.enum([
      "NOT_READY",
      "COLLECTING_EVIDENCE",
      "READY_FOR_POLICY_REVIEW",
      "READY_FOR_PHASE_1_6B",
    ]),
    explanation: z.string(),
    reasons: z.array(z.string()),
    blockers: z.array(z.string()),
    warnings: z.array(z.string()),
    satisfied_criteria: z.array(z.string()),
    recommended_actions: z.array(z.string()),
    policy_version: z.string(),
  }),
});

export type CalibrationReadinessSummary = z.infer<
  typeof calibrationReadinessSummarySchema
>;
export type DashboardMetric = z.infer<typeof metricSchema>;

export function getCalibrationReadiness(): Promise<CalibrationReadinessSummary> {
  return requestJson(
    "/api/v1/internal/calibration-readiness",
    calibrationReadinessSummarySchema,
  );
}
