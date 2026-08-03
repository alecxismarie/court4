import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LandingSessionBoundary } from "@/components/landing/landing-session-boundary";

const replace = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  loading: false,
  user: null as null | { email: string },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => authState,
}));

describe("landing session boundary", () => {
  beforeEach(() => {
    replace.mockReset();
    authState.loading = false;
    authState.user = null;
  });

  it("renders the public landing content for signed-out visitors", () => {
    render(
      <LandingSessionBoundary>
        <p>Public landing</p>
      </LandingSessionBoundary>,
    );
    expect(screen.getByText("Public landing")).toBeInTheDocument();
  });

  it("does not flash public auth content while restoring a session", () => {
    authState.loading = true;
    render(
      <LandingSessionBoundary>
        <p>Public auth form</p>
      </LandingSessionBoundary>,
    );
    expect(screen.queryByText("Public auth form")).not.toBeInTheDocument();
    expect(screen.getByText(/loading court4/i)).toBeInTheDocument();
  });

  it("redirects authenticated users without showing the landing page", () => {
    authState.user = { email: "player@example.com" };
    render(
      <LandingSessionBoundary>
        <p>Public landing</p>
      </LandingSessionBoundary>,
    );
    expect(screen.queryByText("Public landing")).not.toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith("/dashboard");
  });
});
