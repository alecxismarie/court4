import { beforeEach, describe, expect, it } from "vitest";

import { getRecentAnalysisIds, rememberAnalysisId } from "@/lib/recent-analyses";

const storageKey = "court4.recentAnalyses";

describe("recent analysis storage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("stores the newest valid analysis id first without duplicates", () => {
    rememberAnalysisId("analysis-a");
    rememberAnalysisId("analysis-b");
    rememberAnalysisId("analysis-a");

    expect(getRecentAnalysisIds()).toEqual(["analysis-a", "analysis-b"]);
  });

  it("filters invalid persisted values", () => {
    window.localStorage.setItem(
      storageKey,
      JSON.stringify(["analysis-a", "../outside", 12, "analysis_b"]),
    );

    expect(getRecentAnalysisIds()).toEqual(["analysis-a", "analysis_b"]);
  });

  it("keeps only the ten most recent ids", () => {
    for (let index = 0; index < 12; index += 1) {
      rememberAnalysisId(`analysis-${index}`);
    }

    expect(getRecentAnalysisIds()).toEqual([
      "analysis-11",
      "analysis-10",
      "analysis-9",
      "analysis-8",
      "analysis-7",
      "analysis-6",
      "analysis-5",
      "analysis-4",
      "analysis-3",
      "analysis-2",
    ]);
  });
});
