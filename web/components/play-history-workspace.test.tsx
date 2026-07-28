import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PlayHistoryWorkspace } from "@/components/play-history-workspace";
import type { PlayHistoryResponse } from "@/lib/api/types";
import { makePlayHistoryResponse } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const playHistoryMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/use-history", () => ({
  usePlayHistory: playHistoryMock,
}));

describe("play history workspace", () => {
  beforeEach(() => {
    playHistoryMock.mockReturnValue(query(makePlayHistoryResponse()));
  });

  it("explains the empty state in clear player-facing language", () => {
    const response = makePlayHistoryResponse({
      eligible_count: 0,
      comparable_count: 0,
      comparison_candidates: [],
      recent_eligible_analyses: [],
      contributions: [],
    });
    response.progress = {
      ...response.progress,
      status: "NO_QUALIFIED_REPORTS",
      baseline_status: "NO_QUALIFIED_REPORTS",
      answer: "Your progress history hasn't started yet",
      explanation:
        "Court4 needs completed analyses with enough clear, reliable video before it can compare how your play changes over time.",
      qualified_analysis_count: 0,
      comparable_analysis_count: 0,
      qualified_observation_seconds: 0,
      comparison_period_start: null,
      comparison_period_end: null,
      contributing_analysis_ids: [],
      limitations: [
        comparisonDisclaimerForTest,
        "Court4 needs reports with enough reliable information before it can compare them.",
        "Court4 will not guess when information is missing or cannot be compared.",
      ],
    };
    playHistoryMock.mockReturnValue(query(response));

    renderWithQueryClient(<PlayHistoryWorkspace />);

    expect(
      screen.getByRole("heading", { name: "Your progress history hasn't started yet" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/completed analyses with enough clear, reliable video/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Not enough data yet")).toBeInTheDocument();
    expect(screen.getByText("No completed analyses are ready to compare yet.")).toBeInTheDocument();
    expect(screen.getByText("Why no comparison is shown")).toBeInTheDocument();
    expect(
      screen.getByText(/Court4 needs reports with enough reliable information/i),
    ).toBeInTheDocument();
  });

  it("shows the one-report baseline with evidence context and neutral boundaries", () => {
    renderWithQueryClient(<PlayHistoryWorkspace />);

    expect(screen.getByRole("heading", { name: "Your play over time" })).toBeInTheDocument();
    expect(screen.getByText("How has my play changed?")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Building your baseline" })).toBeInTheDocument();
    expect(screen.getByText(/Based on 1 qualified analysis/)).toHaveTextContent(
      /30.0 sec of reliable observation/,
    );
    expect(screen.getByText(/does not show whether your performance got better or worse/i))
      .toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
    expect(
      screen.queryByRole("img", { name: /Neutral graph comparing/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Contribution transparency")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Upload Match" })).not.toBeInTheDocument();
  });

  it("treats exactly three reports as an initial baseline without graphing a trend", () => {
    const reports = comparisonReports().slice(0, 3);
    playHistoryMock.mockReturnValue(
      query(
        makePlayHistoryResponse({
          eligible_count: 3,
          comparable_count: 3,
          comparison_candidates: reports,
          progress: baselineProgress(reports),
        }),
      ),
    );

    renderWithQueryClient(<PlayHistoryWorkspace />);

    expect(
      screen.getByRole("heading", { name: "Initial baseline established" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/One more comparable report is needed/)).toBeInTheDocument();
    expect(
      screen.queryByRole("img", { name: /Neutral graph comparing/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/improved|worsened/i)).not.toBeInTheDocument();
  });

  it("graphs four-report provisional changes with counts, periods, durations, and methods", () => {
    const reports = comparisonReports();
    playHistoryMock.mockReturnValue(
      query(
        makePlayHistoryResponse({
          eligible_count: 4,
          comparable_count: 4,
          comparison_candidates: reports,
          progress: comparisonProgress(reports),
        }),
      ),
    );

    renderWithQueryClient(<PlayHistoryWorkspace />);

    expect(
      screen.getByRole("img", {
        name: "Neutral graph comparing earlier and recent qualified observations",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Provisional comparison").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Observed movement pace (m/s)")).toBeInTheDocument();
    expect(screen.getByText("Increased by 0.2 m/s")).toBeInTheDocument();
    expect(
      screen
        .getAllByText(/2 earlier \+ 2 recent reports/)
        .some((item) =>
          item.textContent?.includes(
            "sum distance metres ÷ sum qualified tracked seconds",
          ),
        ),
    ).toBe(true);
    expect(screen.getAllByText(/2 qualified reports · 1.0 min reliable observation/)).toHaveLength(
      2,
    );
    expect(screen.queryByText(/improved|worsened|more effective/i)).not.toBeInTheDocument();
  });

  it("shows missing graph values as unavailable rather than zero", () => {
    const reports = comparisonReports();
    const progress = comparisonProgress(reports);
    progress.trend_metrics[0] = {
      ...progress.trend_metrics[0],
      recent_value: null,
      change_value: null,
      direction: null,
      recent_contributing_count: 0,
      contributing_analysis_ids: reports.slice(0, 2).map((report) => report.analysis_id),
      provisional: true,
      limitations: ["Missing values are excluded and are never treated as zero."],
    };
    playHistoryMock.mockReturnValue(
      query(
        makePlayHistoryResponse({
          eligible_count: 4,
          comparable_count: 4,
          comparison_candidates: reports,
          progress,
        }),
      ),
    );

    renderWithQueryClient(<PlayHistoryWorkspace />);

    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("0.0 m/s")).not.toBeInTheDocument();
  });

  it("uses descriptive play-style wording with direct measurement context", () => {
    const reports = comparisonReports();
    playHistoryMock.mockReturnValue(
      query(
        makePlayHistoryResponse({
          eligible_count: 4,
          comparable_count: 4,
          comparison_candidates: reports,
          progress: comparisonProgress(reports),
        }),
      ),
    );

    renderWithQueryClient(<PlayHistoryWorkspace />);

    expect(
      screen.getByText(
        /Court4 observed more of your reliably tracked positioning near the kitchen/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Based on 4 qualified reports covering 2.0 min/)).toBeInTheDocument();
    expect(screen.queryByText(/aggressive|defensive|tactical|court control/i))
      .not.toBeInTheDocument();
  });

  it("provides a friendly contributing-report drill-down without internal reason codes", () => {
    const reports = comparisonReports();
    playHistoryMock.mockReturnValue(
      query(
        makePlayHistoryResponse({
          eligible_count: 4,
          comparable_count: 4,
          comparison_candidates: reports,
          progress: comparisonProgress(reports),
        }),
      ),
    );

    renderWithQueryClient(<PlayHistoryWorkspace />);
    fireEvent.click(screen.getByText("Reports considered for this view"));

    expect(screen.getAllByText("Supports this view")).toHaveLength(4);
    expect(screen.getAllByRole("link", { name: "Open analysis" })).toHaveLength(5);
    expect(screen.getByText("Earlier report one")).toBeInTheDocument();
    expect(
      screen.getAllByText(/The report has qualified movement measurements/),
    ).toHaveLength(4);
    expect(screen.queryByText("EVIDENCE_STANDARD_MET")).not.toBeInTheDocument();
  });
});

function comparisonReports(): PlayHistoryResponse["comparison_candidates"] {
  const template = makePlayHistoryResponse().comparison_candidates[0];
  return [
    ["earlier-1", "Earlier report one", "2026-07-10T00:00:00Z"],
    ["earlier-2", "Earlier report two", "2026-07-12T00:00:00Z"],
    ["recent-1", "Recent report one", "2026-07-26T00:00:00Z"],
    ["recent-2", "Recent report two", "2026-07-28T00:00:00Z"],
  ].map(([analysisId, title, createdAt]) => ({
    ...template,
    analysis_id: analysisId,
    title,
    created_at: createdAt,
    report_url: `/matches/${analysisId}/analytics`,
    qualified_observation_seconds: 30,
    qualified_movement_seconds: 24,
  }));
}

function baselineProgress(
  reports: PlayHistoryResponse["comparison_candidates"],
): PlayHistoryResponse["progress"] {
  const base = makePlayHistoryResponse().progress;
  return {
    ...base,
    status: "BASELINE_ESTABLISHED",
    baseline_status: "BASELINE_ESTABLISHED",
    answer: "Initial baseline established",
    explanation:
      "Three comparable reports establish a baseline. Court4 requires at least two reports in both groups.",
    qualified_analysis_count: 3,
    comparable_analysis_count: 3,
    qualified_observation_seconds: 90,
    comparison_period_start: reports[0].created_at,
    comparison_period_end: reports[2].created_at,
    provisional: true,
    trend_eligibility: {
      ...base.trend_eligibility,
      status: "PROVISIONAL",
      reasons: ["Three comparable reports establish an initial baseline only."],
    },
    contributing_analysis_ids: reports.map((report) => report.analysis_id),
  };
}

function comparisonProgress(
  reports: PlayHistoryResponse["comparison_candidates"],
): PlayHistoryResponse["progress"] {
  const base = makePlayHistoryResponse().progress;
  const earlier = reports.slice(0, 2);
  const recent = reports.slice(2);
  return {
    ...base,
    status: "COMPARISON_AVAILABLE",
    baseline_status: "COMPARISON_AVAILABLE",
    answer: "Observed changes are ready to review",
    explanation:
      "Court4 compared your earlier and recent qualified observations using versioned rules.",
    qualified_analysis_count: 4,
    comparable_analysis_count: 4,
    qualified_observation_seconds: 120,
    comparison_period_start: reports[0].created_at,
    comparison_period_end: reports[3].created_at,
    provisional: true,
    earlier_analysis_count: 2,
    recent_analysis_count: 2,
    earlier_group: comparisonGroup("Earlier", earlier),
    recent_group: comparisonGroup("Recent", recent),
    trend_eligibility: {
      ...base.trend_eligibility,
      status: "PROVISIONAL",
      reasons: ["Both groups meet the minimum report-count requirement."],
    },
    interpretation_eligibility: {
      ...base.interpretation_eligibility,
      status: "PROVISIONAL",
      reasons: ["Court4 may describe measured changes using neutral language."],
    },
    contributing_analysis_ids: reports.map((report) => report.analysis_id),
    aggregation_methods: [
      "sum distance metres ÷ sum qualified tracked seconds",
      "sum zone seconds ÷ sum qualified tracked seconds",
    ],
    trend_metrics: [
      trendMetric({
        key: "movement_pace",
        label: "Observed movement pace",
        unit: "m/s",
        earlier_value: 0.7,
        recent_value: 0.9,
        change_value: 0.2,
        direction: "HIGHER",
        aggregation_method: "sum distance metres ÷ sum qualified tracked seconds",
        normalization: "time-normalized movement distance",
        context:
          "Distance is normalized by qualified tracked time. A higher value is not a performance judgment.",
      }),
      trendMetric({
        key: "kitchen_share",
        label: "Observed time near the kitchen",
        unit: "%",
        earlier_value: 35,
        recent_value: 52,
        change_value: 17,
        direction: "HIGHER",
        aggregation_method: "sum zone seconds ÷ sum qualified tracked seconds",
        normalization: "duration-weighted court-zone occupancy",
        context: "Share of qualified tracked time observed near the kitchen.",
      }),
    ],
    play_style: {
      status: "PROVISIONAL_CHANGE",
      metric_key: "kitchen_share",
      metric_label: "Observed time near the kitchen",
      earlier_value: 35,
      recent_value: 52,
      unit: "%",
      summary:
        "Court4 observed more of your reliably tracked positioning near the kitchen in recent qualified analyses (35.0% to 52.0%).",
      qualified_analysis_count: 4,
      qualified_observation_seconds: 120,
      provisional: true,
      limitations: [comparisonDisclaimerForTest],
    },
  };
}

function comparisonGroup(
  name: string,
  reports: PlayHistoryResponse["comparison_candidates"],
): NonNullable<PlayHistoryResponse["progress"]["earlier_group"]> {
  return {
    name,
    period_start: reports[0].created_at,
    period_end: reports[reports.length - 1].created_at,
    analysis_count: reports.length,
    qualified_observation_seconds: 60,
    qualified_movement_seconds: 48,
    analyses: reports,
  };
}

function trendMetric(
  values: Pick<
    PlayHistoryResponse["progress"]["trend_metrics"][number],
    | "key"
    | "label"
    | "unit"
    | "earlier_value"
    | "recent_value"
    | "change_value"
    | "direction"
    | "aggregation_method"
    | "normalization"
    | "context"
  >,
): PlayHistoryResponse["progress"]["trend_metrics"][number] {
  return {
    ...values,
    earlier_contributing_count: 2,
    recent_contributing_count: 2,
    earlier_qualified_observation_seconds: 60,
    recent_qualified_observation_seconds: 60,
    contributing_analysis_ids: ["earlier-1", "earlier-2", "recent-1", "recent-2"],
    provisional: true,
    limitations: ["All eligible observations are retained."],
  };
}

const comparisonDisclaimerForTest =
  "Court4 shows differences between similar recordings. A difference alone does not show whether your performance got better or worse.";

function query(data: PlayHistoryResponse) {
  return {
    data,
    isLoading: false,
    isError: false,
  };
}
