import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardWorkspace } from "@/components/dashboard-workspace";
import { emptyPlayerProfile } from "@/lib/player-profile";
import {
  makeAnalysisHistoryItem,
  makeAnalysisHistoryResponse,
  makePlayHistoryResponse,
} from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

const analysisHistoryMock = vi.hoisted(() => vi.fn());
const playHistoryMock = vi.hoisted(() => vi.fn());
const profileMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/use-history", () => ({
  useAnalysisHistory: analysisHistoryMock,
  usePlayHistory: playHistoryMock,
}));

vi.mock("@/lib/use-player-profile", () => ({
  usePlayerProfile: profileMock,
}));

describe("dashboard workspace", () => {
  beforeEach(() => {
    profileMock.mockReturnValue({
      profile: emptyPlayerProfile,
      isLoaded: true,
      save: vi.fn(),
    });
    analysisHistoryMock.mockReturnValue(query(makeAnalysisHistoryResponse()));
    playHistoryMock.mockReturnValue(query(makePlayHistoryResponse({
      total_analyses: 0,
      eligible_count: 0,
      latest_verified_match_iq: [],
      recent_eligible_analyses: [],
      contributions: [],
    })));
  });

  it("shows a neutral welcome without a configured profile", () => {
    renderWithQueryClient(<DashboardWorkspace />);

    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByText(/Welcome back,/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open player profile" })).toHaveAttribute(
      "href",
      "/player",
    );
    const header = screen.getByRole("heading", { name: "Welcome back" }).closest("section");
    expect(header).not.toBeNull();
    expect(
      within(header as HTMLElement).queryByRole("link", { name: /upload match/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Player workspace")).not.toBeInTheDocument();
  });

  it("shows a personalized welcome with a saved display name", () => {
    profileMock.mockReturnValue({
      profile: { ...emptyPlayerProfile, displayName: "Ava" },
      isLoaded: true,
      save: vi.fn(),
    });

    renderWithQueryClient(<DashboardWorkspace />);

    expect(screen.getByRole("heading", { name: "Welcome back, Ava" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Ava profile photo" })).toHaveTextContent("A");
  });

  it("shows the saved profile photo in the dashboard header", () => {
    profileMock.mockReturnValue({
      profile: {
        ...emptyPlayerProfile,
        displayName: "Alexis",
        profileImageDataUrl: "data:image/png;base64,AQID",
      },
      isLoaded: true,
      save: vi.fn(),
    });

    renderWithQueryClient(<DashboardWorkspace />);

    const avatar = screen.getByRole("img", { name: "Alexis profile photo" });
    expect(avatar.querySelector("img")).toHaveAttribute(
      "src",
      "data:image/png;base64,AQID",
    );
  });

  it("shows a player-facing snapshot and clear report and progress links", () => {
    const item = makeAnalysisHistoryItem();
    analysisHistoryMock.mockReturnValue(query(makeAnalysisHistoryResponse([item])));
    playHistoryMock.mockReturnValue(query(makePlayHistoryResponse()));

    renderWithQueryClient(<DashboardWorkspace />);

    expect(screen.getByText("Total reports")).toBeInTheDocument();
    expect(screen.getByText("Completed reports")).toBeInTheDocument();
    expect(screen.getByText("Qualified analyses")).toBeInTheDocument();
    expect(screen.getByText("Progress check")).toBeInTheDocument();
    expect(screen.getByText("Latest completed analysis")).toBeInTheDocument();
    expect(screen.getByText("Latest verified movement insight")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View Analysis History" })).toHaveAttribute(
      "href",
      "/analysis-history",
    );
    expect(screen.getByRole("link", { name: "View progress" })).toHaveAttribute(
      "href",
      "/my-progress",
    );
    expect(screen.getByText(/Based on 1 qualified analysis/)).toHaveTextContent(
      /30.0 sec of reliable observation/,
    );
    expect(screen.getByText(/Provisional\.$/)).toBeInTheDocument();
    expect(screen.queryByText(/Included because recording quality/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/cumulative distance/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/score/i)).not.toBeInTheDocument();
  });
});

function query<T>(data: T) {
  return {
    data,
    isLoading: false,
    isError: false,
  };
}
