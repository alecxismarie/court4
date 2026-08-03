import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  LandingAuthPanel,
  safeLandingDestination,
} from "@/components/landing/landing-auth-panel";

const replace = vi.hoisted(() => vi.fn());
const login = vi.hoisted(() => vi.fn());
const register = vi.hoisted(() => vi.fn());
const searchParams = vi.hoisted(() => new URLSearchParams());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams,
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ login, register }),
}));

describe("landing authentication panel", () => {
  beforeEach(() => {
    replace.mockReset();
    login.mockReset().mockResolvedValue(undefined);
    register.mockReset().mockResolvedValue(undefined);
    searchParams.delete("next");
  });

  it("logs in with the existing auth context and routes to the dashboard", async () => {
    const user = userEvent.setup();
    render(<LandingAuthPanel />);

    await user.type(screen.getByLabelText(/^email$/i), "player@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /^log in$/i }));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith("player@example.com", "correct horse battery");
      expect(replace).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("registers through the existing flow and opens verification pending", async () => {
    const user = userEvent.setup();
    render(<LandingAuthPanel />);

    await user.click(screen.getByRole("tab", { name: /sign up/i }));
    await user.type(screen.getByLabelText(/^email$/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "a long secure password");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(register).toHaveBeenCalledWith("new@example.com", "a long secure password");
      expect(replace).toHaveBeenCalledWith("/verification-pending");
    });
  });

  it("supports keyboard tab switching and labels planned social providers honestly", async () => {
    const user = userEvent.setup();
    render(<LandingAuthPanel />);

    const loginTab = screen.getByRole("tab", { name: /log in/i });
    fireEvent.keyDown(loginTab, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: /sign up/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await user.click(screen.getByRole("button", { name: /continue with google/i }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Google sign-in is coming soon",
    );
    expect(login).not.toHaveBeenCalled();
  });
});

describe("safe landing destination", () => {
  it.each([
    [null, "/dashboard"],
    ["", "/dashboard"],
    ["https://malicious.example", "/dashboard"],
    ["//malicious.example", "/dashboard"],
    ["/\\malicious.example", "/dashboard"],
    ["/https://malicious.example", "/dashboard"],
    ["/matches/analysis-1?tab=analytics", "/matches/analysis-1?tab=analytics"],
  ])("maps %s to %s", (value, expected) => {
    expect(safeLandingDestination(value)).toBe(expected);
  });
});
