import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGate } from "@/components/auth-gate";

const replace = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  loading: false,
  user: null as null | { email: string; email_verified_at: string | null },
}));
const navigationState = vi.hoisted(() => ({
  pathname: "/matches/analysis-1",
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigationState.pathname,
  useSearchParams: () => new URLSearchParams("tab=analytics"),
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => authState,
}));

describe("protected route gate", () => {
  beforeEach(() => {
    replace.mockReset();
    authState.loading = false;
    authState.user = null;
    navigationState.pathname = "/matches/analysis-1";
  });

  it("redirects unauthenticated users with their intended destination", async () => {
    render(<AuthGate>Private workspace</AuthGate>);
    expect(await screen.findByText("Loading…")).toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith(
      "/?auth=login&next=%2Fmatches%2Fanalysis-1%3Ftab%3Danalytics",
    );
  });

  it("renders protected content only for a verified authenticated user", () => {
    authState.user = {
      email: "player@example.com",
      email_verified_at: "2026-08-04T00:00:00Z",
    };
    render(<AuthGate>Private workspace</AuthGate>);
    expect(screen.getByText("Private workspace")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it.each(["/dashboard", "/analyses", "/play-history", "/settings"])(
    "redirects an unverified user away from %s without rendering it",
    (pathname) => {
      navigationState.pathname = pathname;
      authState.user = { email: "player@example.com", email_verified_at: null };
      render(<AuthGate>Private workspace</AuthGate>);

      expect(screen.queryByText("Private workspace")).not.toBeInTheDocument();
      expect(replace).toHaveBeenCalledWith("/verification-pending");
    },
  );

  it("keeps verification pending available to an unverified user", () => {
    navigationState.pathname = "/verification-pending";
    authState.user = { email: "player@example.com", email_verified_at: null };
    render(<AuthGate>Activation</AuthGate>);
    expect(screen.getByText("Activation")).toBeInTheDocument();
  });

  it("returns a signed-out verification-pending visit to the public landing page", () => {
    navigationState.pathname = "/verification-pending";
    authState.user = null;
    render(<AuthGate>Activation</AuthGate>);
    expect(screen.queryByText("Activation")).not.toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("renders the public landing route for an unauthenticated visitor", () => {
    navigationState.pathname = "/";
    render(<AuthGate>Public landing</AuthGate>);
    expect(screen.getByText("Public landing")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
