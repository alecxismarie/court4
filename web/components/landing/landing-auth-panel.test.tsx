import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  LandingAuthPanel,
} from "@/components/landing/landing-auth-panel";
import { safeLandingDestination } from "@/lib/auth-redirect";

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
    login.mockReset().mockResolvedValue({ email_verified_at: "2026-08-04T00:00:00Z" });
    register.mockReset().mockResolvedValue({ email_verified_at: null });
    searchParams.delete("next");
    searchParams.delete("auth");
  });

  it("routes an existing unverified login only to account activation", async () => {
    login.mockResolvedValueOnce({ email_verified_at: null });
    const user = userEvent.setup();
    render(<LandingAuthPanel />);
    await user.type(screen.getByLabelText(/^email$/i), "pending@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /^log in$/i }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/verification-pending"));
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

  it("does not claim configurable session persistence", () => {
    render(<LandingAuthPanel />);

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/remember me|keep me signed in/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /forgot password/i })).toBeVisible();
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

  it("opens the requested Sign Up tab from the consolidated auth route", () => {
    searchParams.set("auth", "signup");
    render(<LandingAuthPanel />);

    expect(screen.getByRole("tab", { name: /sign up/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("heading", { name: /create your account/i })).toBeVisible();
  });

  it("supports keyboard tab switching and renders crisp social provider controls", async () => {
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
      "Google sign-in is not available",
    );
    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Continue with Apple" })).toBeVisible();
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
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
