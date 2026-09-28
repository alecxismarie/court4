import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MatchDeletionControls } from "@/components/match-deletion-controls";
import { deleteMatch, getMatchLifecycle } from "@/lib/api/source-media";
import { renderWithQueryClient } from "@/test/render";

vi.mock("@/lib/api/source-media", () => ({ deleteMatch: vi.fn(), getMatchLifecycle: vi.fn() }));
describe("whole match deletion", () => {
  beforeEach(() => { vi.mocked(deleteMatch).mockReset(); vi.mocked(getMatchLifecycle).mockResolvedValue({ analysis_id: "match-1", state: "deleted" }); });
  it("requires separate confirmation and removes only this match's cached report", async () => {
    const user = userEvent.setup();
    vi.mocked(deleteMatch).mockResolvedValue(undefined);
    renderWithQueryClient(<MatchDeletionControls analysisId="match-1" />);
    await user.click(screen.getByRole("button", { name: "Delete match & analysis" }));
    expect(deleteMatch).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete match & analysis" }));
    await user.click(screen.getByRole("button", { name: "Permanently delete match & analysis" }));
    expect(await screen.findByRole("status")).toHaveTextContent("no longer contributes");
    expect(deleteMatch).toHaveBeenCalledWith("match-1");
  });
  it("shows pending removal honestly and permits a retry after provider failure", async () => {
    const user = userEvent.setup();
    vi.mocked(deleteMatch).mockRejectedValueOnce(new Error("Please retry")).mockResolvedValueOnce(undefined);
    vi.mocked(getMatchLifecycle).mockResolvedValue({ analysis_id: "match-1", state: "deletion_pending" });
    renderWithQueryClient(<MatchDeletionControls analysisId="match-1" state="deletion_pending" />);
    expect(screen.getByRole("status")).toHaveTextContent("excluded from History and Progress");
    await user.click(screen.getByRole("button", { name: "Retry match deletion" }));
    await user.click(screen.getByRole("button", { name: "Permanently delete match & analysis" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please retry");
    await user.click(screen.getByRole("button", { name: "Permanently delete match & analysis" }));
    expect(await screen.findByText(/Match and analysis deleted/)).toBeInTheDocument();
  });
});
