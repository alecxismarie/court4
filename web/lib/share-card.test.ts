import { describe, expect, it } from "vitest";

import { buildShareCardData, getShareCardFormat } from "@/lib/share-card";
import { makeAnalyticsReport, makeMatchIQReport } from "@/test/factories";

describe("share card data", () => {
  it("derives card content from persisted analytics and Match IQ fields", () => {
    const data = buildShareCardData({
      analytics: makeAnalyticsReport(),
      matchIQ: makeMatchIQReport(),
      playerName: "  Ava  ",
      artifact: "heatmap",
      resultsUrl: "https://court4.example/matches/analysis-123/analytics",
    });

    expect(data).toMatchObject({
      analysisId: "analysis-123",
      playerName: "Ava",
      matchDate: "Jul 21, 2026",
      totalDistance: { value: 42.5, unit: "ft" },
      zones: { kitchen: 20, transition: 40, baseline: 40 },
      artifactLabel: "Heatmap",
      resultsUrl: "https://court4.example/matches/analysis-123/analytics",
    });
    expect(data.artifactUrl).toBe("/api/share-artifact/analysis-123/analytics/heatmap.png");
    expect(data.summary).toContain("Match IQ found 3 movement observations");
    expect(data.insights).toHaveLength(2);
    expect(data.focus).toContain("Focus area: positioning mix");
    expect(data).not.toHaveProperty("selected_player_track_id");
  });

  it("supports analytics-only legacy results without fabricating Match IQ content", () => {
    const data = buildShareCardData({
      analytics: makeAnalyticsReport(),
      matchIQ: null,
      playerName: "",
      artifact: "none",
    });

    expect(data.playerName).toBe("Local Player");
    expect(data.summary).toBeUndefined();
    expect(data.insights).toEqual([]);
    expect(data.focus).toBeUndefined();
    expect(data.artifactUrl).toBeUndefined();
  });

  it("exposes required social formats", () => {
    expect(getShareCardFormat("story")).toMatchObject({ width: 1080, height: 1920 });
    expect(getShareCardFormat("portrait")).toMatchObject({ width: 1080, height: 1350 });
    expect(getShareCardFormat("square")).toMatchObject({ width: 1080, height: 1080 });
  });
});
