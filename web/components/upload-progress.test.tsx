import { render, screen } from "@testing-library/react";

import { UploadProgress } from "@/components/upload-progress";

describe("UploadProgress", () => {
  it("shows a true zero and distinguishes preparation from network bytes", () => {
    const view = render(<UploadProgress progress={{ loaded: 0, total: 100, percent: 0, phase: "uploading" }} />);
    expect(screen.getByRole("progressbar").firstElementChild).toHaveStyle({ width: "0%" });
    view.rerender(<UploadProgress progress={{ loaded: 0, total: 100, percent: null, phase: "preparing" }} />);
    expect(screen.getByText("Preparing video")).toBeInTheDocument();
    expect(screen.getByText(/No video bytes are being sent yet/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  });
  it("uses the Court4 brand lime token for the progress fill", () => {
    render(<UploadProgress progress={{ loaded: 50, total: 100, percent: 50 }} />);

    const fill = screen.getByRole("progressbar").firstElementChild;

    expect(fill).toHaveClass("bg-court-lime");
    expect(fill).not.toHaveClass("bg-court-blue");
  });

  it("distinguishes completed transfer from server verification", () => {
    render(
      <UploadProgress
        progress={{ loaded: 100, total: 100, percent: 100, phase: "verifying" }}
      />,
    );

    expect(screen.getByText("Verifying and finalizing video")).toBeInTheDocument();
    expect(screen.getByText("Upload complete")).toBeInTheDocument();
    expect(screen.getByText(/your analysis is not complete yet/)).toBeInTheDocument();
  });
});
