import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalyticsDetails } from "@/components/analytics-details";
import { getAnalytics } from "@/lib/api/analyses";
import { makeAnalyticsReport } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

vi.mock("@/lib/api/analyses", () => ({
  getAnalytics: vi.fn(),
}));

const mockedGetAnalytics = vi.mocked(getAnalytics);

describe("analytics details", () => {
  beforeEach(() => {
    mockedGetAnalytics.mockReset();
  });

  it("renders factual metrics and existing analytics images", async () => {
    mockedGetAnalytics.mockResolvedValue({
      analysis_id: "analysis-123",
      analytics: makeAnalyticsReport(),
    });

    renderWithQueryClient(<AnalyticsDetails analysisId="analysis-123" />);

    expect(await screen.findByText("42.5 ft")).toBeInTheDocument();
    expect(screen.getByText("Selected track 1 - calibration auto-court-detection")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Heatmap" })).toHaveAttribute(
      "src",
      "http://localhost:8000/api/v1/analyses/analysis-123/artifacts/analytics/heatmap.png",
    );
    expect(screen.getByRole("img", { name: "Trajectory" })).toBeInTheDocument();
  });
});
