import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SampledFrames } from "@/components/sampled-frames";
import { makeFrame } from "@/test/factories";

describe("sampled frames", () => {
  it("renders sampled frame artifacts with API-backed image URLs", () => {
    render(
      <SampledFrames
        analysisId="analysis-123"
        frames={[makeFrame()]}
        isLoading={false}
      />,
    );

    expect(screen.getByText("frame_000001.jpg")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Sampled frame 1" })).toHaveAttribute(
      "src",
      "http://localhost:8000/api/v1/analyses/analysis-123/artifacts/frames/frame_000001.jpg",
    );
  });

  it("renders an empty state before frames exist", () => {
    render(<SampledFrames analysisId="analysis-123" frames={[]} isLoading={false} />);

    expect(screen.getByText("No sampled frames yet")).toBeInTheDocument();
  });
});
