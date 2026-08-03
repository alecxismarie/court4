import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PrivacyPage from "@/app/privacy/page";
import TermsPage from "@/app/terms/page";

describe("private-alpha legal routes", () => {
  it("renders privacy video and deletion disclosures", () => {
    render(<PrivacyPage />);
    expect(screen.getByRole("heading", { name: "Privacy Policy" })).toBeInTheDocument();
    expect(screen.getByText(/players, spectators/i)).toBeInTheDocument();
    expect(screen.getByText(/retention\/deletion engine is not yet available/i)).toBeInTheDocument();
  });

  it("renders terms upload ownership and alpha limitations", () => {
    render(<TermsPage />);
    expect(screen.getByRole("heading", { name: "Terms of Service" })).toBeInTheDocument();
    expect(screen.getByText(/retain ownership/i)).toBeInTheDocument();
    expect(screen.getByText(/automatic recording/i)).toBeInTheDocument();
  });
});
