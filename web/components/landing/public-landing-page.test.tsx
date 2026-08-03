import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PublicLandingPage } from "@/components/landing/public-landing-page";
import {
  journeySteps,
  landingStatistics,
} from "@/lib/landing-content";

vi.mock("@/components/landing/landing-auth-panel", () => ({
  LandingAuthPanel: () => <section aria-label="Court4 account access">Account access</section>,
}));

describe("public Court4 landing page", () => {
  it("renders every approved content section in order", () => {
    const { container } = render(<PublicLandingPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "KnowYour Game.ElevateEvery Match.",
    );
    expect(screen.getByRole("heading", { name: /your journey with court4/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /data that drives/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /apparel & paddle store/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /partner program in development/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /stay ahead of the game/i })).toBeInTheDocument();

    const sectionIds = Array.from(container.querySelectorAll("main section[id]")).map(
      (section) => section.id,
    );
    expect(sectionIds).toEqual([
      "about",
      "journey",
      "features",
      "partner-clubs",
      "newsletter",
    ]);
  });

  it("uses truthful alpha status and current upload-first journey copy", () => {
    render(<PublicLandingPage />);

    for (const statistic of landingStatistics) {
      expect(screen.getByText(statistic.value)).toBeInTheDocument();
      expect(screen.getByText(statistic.label)).toBeInTheDocument();
    }
    for (const step of journeySteps) {
      expect(screen.getByRole("heading", { name: `${step.number}. ${step.title}` })).toBeInTheDocument();
      expect(screen.getByText(step.copy)).toBeInTheDocument();
    }

    expect(screen.getByText(/has not announced club partners/i)).toBeInTheDocument();
    expect(screen.queryByText(/10K\+|5K\+|95%|20% OFF/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/terms");
  });

  it("exposes accessible navigation and visual alternative text", () => {
    render(<PublicLandingPage />);

    expect(screen.getByRole("link", { name: /skip to main content/i })).toHaveAttribute(
      "href",
      "#landing-main",
    );
    expect(screen.getByRole("navigation", { name: /primary navigation/i })).toBeInTheDocument();
    expect(screen.queryByText(/AI-powered match intelligence/i)).not.toBeInTheDocument();
    expect(screen.getAllByAltText("Court4")[0]).toHaveAttribute(
      "src",
      expect.stringContaining("court4-logo.png"),
    );
    expect(screen.getByAltText(/match iq score/i)).toBeInTheDocument();
    expect(screen.getByAltText(/performance shirt/i)).toBeInTheDocument();
  });
});
