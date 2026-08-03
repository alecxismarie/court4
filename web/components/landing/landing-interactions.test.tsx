import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  MobileLandingMenu,
  NewsletterForm,
  PlannedFeatureAction,
} from "@/components/landing/landing-interactions";

describe("landing page planned interactions", () => {
  it("opens and closes the accessible mobile menu", async () => {
    const user = userEvent.setup();
    render(
      <MobileLandingMenu>
        <a href="#features">Features</a>
      </MobileLandingMenu>,
    );

    const toggle = screen.getByRole("button", { name: /open navigation menu/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(screen.getByRole("navigation", { name: /mobile landing navigation/i })).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.click(toggle);
    expect(screen.queryByRole("navigation", { name: /mobile landing navigation/i })).not.toBeInTheDocument();
  });

  it("never pretends to submit or store a newsletter address", async () => {
    const user = userEvent.setup();
    render(<NewsletterForm />);

    await user.type(screen.getByLabelText(/email address/i), "player@example.com");
    await user.click(screen.getByRole("button", { name: /join the list/i }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Your email was not stored or submitted",
    );
  });

  it("discloses planned features without navigating", async () => {
    const user = userEvent.setup();
    render(
      <PlannedFeatureAction message="The store is planned.">
        Shop now
      </PlannedFeatureAction>,
    );
    await user.click(screen.getByRole("button", { name: /shop now/i }));
    expect(screen.getByRole("status")).toHaveTextContent("The store is planned.");
  });
});
