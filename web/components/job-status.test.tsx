import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  JobStatus,
  getCurrentWorkflowStep,
  getStageLabel,
  getStatusLabel,
} from "@/components/job-status";
import { makeJob } from "@/test/factories";

describe("job status labels", () => {
  it("renders player-friendly workflow labels and progress", () => {
    render(
      <JobStatus
        job={makeJob({
          current_stage: "tracked",
          inspection_completed: true,
          calibration_completed: true,
          tracking_completed: true,
          status: "processing",
        })}
      />,
    );

    expect(screen.queryByText("Processing")).not.toBeInTheDocument();
    expect(screen.getByText("Match uploaded")).toBeInTheDocument();
    expect(screen.getByText("Court recognized")).toBeInTheDocument();
    expect(screen.getByText("Players identified")).toBeInTheDocument();
    expect(screen.getAllByText("Select yourself")[0]).toBeInTheDocument();
    expect(screen.getByText("Your Match IQ")).toBeInTheDocument();
    expect(screen.getByText("3 of 5 steps complete")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Workflow completion progress" }))
      .toHaveAttribute("aria-valuenow", "60");
  });

  it("humanizes unknown labels from future backend stages", () => {
    expect(getStatusLabel("queued_for_review")).toBe("Queued For Review");
    expect(getStageLabel("court_verified")).toBe("Court Verified");
  });

  it("returns a precise active step label", () => {
    expect(
      getCurrentWorkflowStep(
        makeJob({
          calibration_completed: true,
          tracking_completed: false,
        }),
      ).currentLabel,
    ).toBe("Finding players");
  });
});
