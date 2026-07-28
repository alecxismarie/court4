import { describe, expect, it, vi } from "vitest";

const redirectMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

import MatchesPage from "@/app/matches/page";
import AnalysesPage from "@/app/analyses/page";
import LegacyUploadMatchPage from "@/app/matches/upload/page";
import PerformancePage from "@/app/performance/page";
import PlayHistoryPage from "@/app/play-history/page";

describe("legacy history redirects", () => {
  it("redirects Matches to Analysis History", () => {
    MatchesPage();
    expect(redirectMock).toHaveBeenCalledWith("/analysis-history");
  });

  it("redirects the old Analyses URL to Analysis History", () => {
    AnalysesPage();
    expect(redirectMock).toHaveBeenCalledWith("/analysis-history");
  });

  it("redirects the old nested Upload Match URL", () => {
    LegacyUploadMatchPage();
    expect(redirectMock).toHaveBeenCalledWith("/upload-match");
  });

  it("redirects Performance to My Progress", () => {
    PerformancePage();
    expect(redirectMock).toHaveBeenCalledWith("/my-progress");
  });

  it("redirects the old Play History URL to My Progress", () => {
    PlayHistoryPage();
    expect(redirectMock).toHaveBeenCalledWith("/my-progress");
  });
});
