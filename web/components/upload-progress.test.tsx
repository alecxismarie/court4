import { render, screen } from "@testing-library/react";

import { UploadProgress } from "@/components/upload-progress";

describe("UploadProgress", () => {
  it("uses the Court4 brand lime token for the progress fill", () => {
    render(<UploadProgress progress={{ loaded: 50, total: 100, percent: 50 }} />);

    const fill = screen.getByRole("progressbar").firstElementChild;

    expect(fill).toHaveClass("bg-court-lime");
    expect(fill).not.toHaveClass("bg-court-blue");
  });
});
