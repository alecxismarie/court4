import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JobStatus, getStageLabel, getStatusLabel } from "@/components/job-status";
import { makeJob } from "@/test/factories";

describe("job status labels", () => {
  it("maps known backend status and stage values", () => {
    render(
      <JobStatus
        job={makeJob({
          current_stage: "tracked",
          inspection_completed: true,
          calibration_completed: true,
          status: "processing",
        })}
      />,
    );

    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Players tracked")).toBeInTheDocument();
    expect(screen.getByText("Video uploaded and inspected")).toBeInTheDocument();
  });

  it("humanizes unknown labels from future backend stages", () => {
    expect(getStatusLabel("queued_for_review")).toBe("Queued For Review");
    expect(getStageLabel("court_verified")).toBe("Court Verified");
  });
});
