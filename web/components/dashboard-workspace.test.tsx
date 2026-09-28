import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
const authMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/use-history", () => ({
  useAnalysisHistory: analysisHistoryMock,
  usePlayHistory: playHistoryMock,
}));

vi.mock("@/lib/use-player-profile", () => ({
  usePlayerProfile: profileMock,
}));

vi.mock("@/lib/auth-context", () => ({
  useOptionalAuth: authMock,
}));

describe("dashboard workspace", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    authMock.mockReturnValue(null);
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

    expect(screen.getByRole("heading", { name: "Welcome back!" })).toBeInTheDocument();
    expect(screen.queryByText(/Welcome back,/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open player profile" })).toHaveAttribute(
      "href",
      "/player",
    );
    const header = screen.getByRole("heading", { name: "Welcome back!" }).closest("section");
    expect(header).not.toBeNull();
    expect(header).toHaveClass("md:rounded-md", "md:bg-white", "md:shadow-panel");
    expect(screen.getByRole("heading", { name: "Welcome back!" })).toHaveClass(
      "md:text-court-ink",
    );
    expect(
      within(header as HTMLElement).queryByRole("link", { name: /upload match/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Player workspace")).not.toBeInTheDocument();
    const firstAnalysisHeading = screen.getByRole("heading", {
      name: "Your first analysis starts here",
    });
    expect(firstAnalysisHeading.closest("section")).toHaveClass("md:hidden");
    expect(screen.getByRole("link", { name: "Upload a match" })).toHaveAttribute(
      "href",
      "/upload-match",
    );
    expect(screen.getByRole("region", { name: "Dashboard actions" })).toHaveClass(
      "hidden",
      "md:flex",
    );
    expect(
      screen.getByText("No completed analysis is available yet.").closest("section"),
    ).toHaveClass("hidden", "md:grid");
    expect(screen.getByText(/No verified movement insight is available/)).toBeInTheDocument();
  });

  it("uses authoritative completed counts beyond the visible page", () => {
    analysisHistoryMock.mockReturnValue(query({ ...makeAnalysisHistoryResponse([makeAnalysisHistoryItem()]), total: 150, completed_total: 120 }));
    renderWithQueryClient(<DashboardWorkspace />);
    expect(screen.getByText("Total reports").parentElement?.parentElement).toHaveTextContent("150");
    expect(screen.getByText("Completed reports").parentElement?.parentElement).toHaveTextContent("120");
  });

  it.each(["history", "progress"])("distinguishes %s failure from empty and offers retry", async (failed) => {
    const retry = vi.fn();
    analysisHistoryMock.mockReturnValue({ ...query(makeAnalysisHistoryResponse()), isError: failed === "history", refetch: retry });
    playHistoryMock.mockReturnValue({ ...query(makePlayHistoryResponse()), isError: failed === "progress", refetch: retry });
    renderWithQueryClient(<DashboardWorkspace />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
    expect(screen.queryByText("Your first analysis starts here")).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry dashboard" }));
    expect(retry).toHaveBeenCalledTimes(2);
  });

  it("shows a personalized welcome with a saved display name", () => {
    profileMock.mockReturnValue({
      profile: { ...emptyPlayerProfile, displayName: "Ava" },
      isLoaded: true,
      save: vi.fn(),
    });

    renderWithQueryClient(<DashboardWorkspace />);

    expect(screen.getByRole("heading", { name: "Welcome back, Ava!" })).toBeInTheDocument();
    expect(
      screen.getByText("Review your latest report and see how your game is developing over time."),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Ava profile photo" })).toHaveTextContent("A");
  });

  it("welcomes a newly onboarded player without saying welcome back", async () => {
    const userId = "56ae6283-69ee-44b6-9f19-6bf9dc1d7092";
    authMock.mockReturnValue({ user: { id: userId, last_login_at: null } });
    profileMock.mockReturnValue({
      profile: { ...emptyPlayerProfile, displayName: "Mimi" },
      isLoaded: true,
      save: vi.fn(),
    });

    renderWithQueryClient(<DashboardWorkspace />);

    expect(
      await screen.findByRole("heading", { name: "Welcome, Mimi" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Start uploading your matches and see how your game is developing over time.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Welcome back, Mimi!" })).not.toBeInTheDocument();
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
