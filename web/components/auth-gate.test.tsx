import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGate } from "@/components/auth-gate";

const replace = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  loading: false,
  user: null as null | { email: string },
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
      "/login?next=%2Fmatches%2Fanalysis-1%3Ftab%3Danalytics",
    );
  });

  it("renders protected content for an authenticated user", () => {
    authState.user = { email: "player@example.com" };
    render(<AuthGate>Private workspace</AuthGate>);
    expect(screen.getByText("Private workspace")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("renders the public landing route for an unauthenticated visitor", () => {
    navigationState.pathname = "/";
    render(<AuthGate>Public landing</AuthGate>);
    expect(screen.getByText("Public landing")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
