import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LandingSessionBoundary } from "@/components/landing/landing-session-boundary";

const replace = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  loading: false,
  user: null as null | { email: string; email_verified_at: string | null },
}));
const searchParams = vi.hoisted(() => new URLSearchParams());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams,
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => authState,
}));

describe("landing session boundary", () => {
  beforeEach(() => {
    replace.mockReset();
    authState.loading = false;
    authState.user = null;
    searchParams.delete("next");
  });

  it("renders the public landing content for signed-out visitors", () => {
    render(
      <LandingSessionBoundary>
        <p>Public landing</p>
      </LandingSessionBoundary>,
    );
    expect(screen.getByText("Public landing")).toBeInTheDocument();
  });

  it("renders a deterministic hydration shell on the server", () => {
    const html = renderToString(
      <LandingSessionBoundary>
        <p>Public landing</p>
      </LandingSessionBoundary>,
    );

    expect(html).toContain("landing-session-loading");
    expect(html).toContain("Loading Court4");
    expect(html).not.toContain("Public landing");
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
    authState.user = {
      email: "player@example.com",
      email_verified_at: "2026-08-03T00:00:00Z",
    };
    render(
      <LandingSessionBoundary>
        <p>Public landing</p>
      </LandingSessionBoundary>,
    );
    expect(screen.queryByText("Public landing")).not.toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith("/dashboard");
  });

  it("preserves a safe next route and rejects an external destination", () => {
    authState.user = {
      email: "player@example.com",
      email_verified_at: "2026-08-03T00:00:00Z",
    };
    searchParams.set("next", "/upload-match");
    const view = render(
      <LandingSessionBoundary>
        <p>Public landing</p>
      </LandingSessionBoundary>,
    );
    expect(replace).toHaveBeenLastCalledWith("/upload-match");

    searchParams.set("next", "https://malicious.example");
    view.rerender(
      <LandingSessionBoundary>
        <p>Public landing</p>
      </LandingSessionBoundary>,
    );
    expect(replace).toHaveBeenLastCalledWith("/dashboard");
  });

  it("keeps a newly registered unverified account on verification pending", () => {
    authState.user = { email: "new@example.com", email_verified_at: null };
    render(
      <LandingSessionBoundary>
        <p>Public landing</p>
      </LandingSessionBoundary>,
    );

    expect(replace).toHaveBeenCalledWith("/verification-pending");
  });
});
