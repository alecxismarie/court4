import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalysisHistoryWorkspace } from "@/components/analysis-history-workspace";
import {
  makeAnalysisHistoryItem,
  makeAnalysisHistoryResponse,
} from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const historyMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/use-history", () => ({
  useAnalysisHistory: historyMock,
}));

describe("analysis history workspace", () => {
  beforeEach(() => {
    historyMock.mockReturnValue(query(makeAnalysisHistoryResponse()));
  });

  it("shows the player-facing empty state", () => {
    renderWithQueryClient(<AnalysisHistoryWorkspace />);

    expect(screen.getByText("Past reports")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Your analysis history" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /upload match/i })).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "No analyses yet. Upload a match recording to create your first Court4 report.",
      ),
    ).toBeInTheDocument();
  });

  it.each([
    [16.96666666666666 / 61.2, "28%"],
    [null, "Not available"],
  ])("renders whole-video coverage %s", (coverage, expected) => {
    historyMock.mockReturnValue(query(makeAnalysisHistoryResponse([
      makeAnalysisHistoryItem({ observation_coverage_ratio: coverage }),
    ])));
    renderWithQueryClient(<AnalysisHistoryWorkspace />);
    const fact = screen.getByText("Observation coverage").parentElement;
    expect(fact).not.toBeNull();
    expect(within(fact!).getByText(expected)).toBeInTheDocument();
    expect(screen.queryByText("69%")).not.toBeInTheDocument();
  });

  it("pages beyond 100 and resets the server filter to its first page", async () => {
    historyMock.mockImplementation((options) => query({
      ...makeAnalysisHistoryResponse([makeAnalysisHistoryItem({ title: `Record ${options.offset}` })]),
      total: 101,
      offset: options.offset,
    }));
    const user = userEvent.setup();
    renderWithQueryClient(<AnalysisHistoryWorkspace />);
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Record 100")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Ready" }));
    expect(historyMock).toHaveBeenLastCalledWith({ limit: 100, offset: 0, status: "READY" });
  });

  it("does not offer another page for exactly 100 records", () => {
    historyMock.mockReturnValue(query({ ...makeAnalysisHistoryResponse(), total: 100 }));
    renderWithQueryClient(<AnalysisHistoryWorkspace />);
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("shows processing, ready, limited, unsuitable, failed, and legacy analyses", () => {
    const items = [
      makeAnalysisHistoryItem({ analysis_id: "ready", title: "Ready recording" }),
      makeAnalysisHistoryItem({
        analysis_id: "processing",
        title: "Processing recording",
        status: "PROCESSING",
        measurement_available: false,
        match_iq_available: false,
        contribution: {
          ...makeAnalysisHistoryItem().contribution,
          status: "PROVISIONAL",
          explanation: "This analysis will be evaluated after processing is complete.",
        },
      }),
      makeAnalysisHistoryItem({
        analysis_id: "limited",
        title: "Limited recording",
        status: "LIMITED",
        recording_quality: "LIMITED",
      }),
      makeAnalysisHistoryItem({
        analysis_id: "unsuitable",
        title: "Unsuitable recording title",
        status: "UNSUITABLE",
        recording_quality: "UNSUITABLE",
        contribution: {
          ...makeAnalysisHistoryItem().contribution,
          status: "EXCLUDED",
          reason_codes: ["UNSUITABLE_RECORDING"],
          explanation:
            "This analysis remains in your history but does not contribute to Play History.",
        },
      }),
      makeAnalysisHistoryItem({
        analysis_id: "failed",
        title: "Failed recording",
        status: "FAILED",
      }),
      makeAnalysisHistoryItem({
        analysis_id: "legacy",
        title: "Legacy recording",
        status: "LEGACY",
        contribution: {
          ...makeAnalysisHistoryItem().contribution,
          status: "NOT_EVALUATED",
          reason_codes: ["LEGACY_EVIDENCE_UNAVAILABLE"],
          explanation: "This legacy analysis is saved but not yet evaluated.",
        },
      }),
    ];
    historyMock.mockReturnValue(query(makeAnalysisHistoryResponse(items)));

    renderWithQueryClient(<AnalysisHistoryWorkspace />);

    expect(screen.getAllByText("Processing").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Ready").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Limited evidence")).toBeInTheDocument();
    expect(screen.getByText("Unsuitable recording")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Legacy analysis")).toBeInTheDocument();
    expect(screen.getAllByText("Included in Play History").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Excluded from Play History")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /reopen report/i })).toHaveLength(6);
    expect(screen.queryByText("UNSUITABLE_RECORDING")).not.toBeInTheDocument();
    expect(screen.queryByText("LEGACY_EVIDENCE_UNAVAILABLE")).not.toBeInTheDocument();
  });

  it("filters statuses without removing them from persisted history", async () => {
    historyMock.mockReturnValue(
      query(
        makeAnalysisHistoryResponse([
          makeAnalysisHistoryItem({ analysis_id: "ready", title: "Ready recording" }),
          makeAnalysisHistoryItem({
            analysis_id: "limited",
            title: "Limited recording",
            status: "LIMITED",
          }),
        ]),
      ),
    );
    const user = userEvent.setup();

    renderWithQueryClient(<AnalysisHistoryWorkspace />);
    await user.click(screen.getByRole("button", { name: "Limited" }));

    expect(screen.getByText("Limited recording")).toBeInTheDocument();
    expect(screen.queryByText("Ready recording")).not.toBeInTheDocument();
  });
});

function query(data: ReturnType<typeof makeAnalysisHistoryResponse>) {
  return {
    data,
    isLoading: false,
    isError: false,
  };
}
