import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccountQueryProvider } from "@/lib/account-query-provider";
import { AuthProvider, useAuth } from "@/lib/auth-context";

const api = vi.hoisted(() => ({ login: vi.fn(), logout: vi.fn(), restoreSession: vi.fn() }));
vi.mock("@/lib/api/auth", () => ({ ...api, register: vi.fn(), verifyEmail: vi.fn(), completeOnboarding: vi.fn() }));
const replace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
const observations: string[] = [];
function account(id: string) { return { id, email: `${id}@example.test`, display_name: id, email_verified_at: "2026-09-28" }; }
function PrivateData() {
  const { user } = useAuth();
  const history = useQuery({ queryKey: ["analysis-history"], queryFn: async () => `${user!.id} history` });
  const progress = useQuery({ queryKey: ["play-history"], queryFn: async () => `${user!.id} progress` });
  const text = `${user!.id}: ${history.data ?? "loading"} / ${progress.data ?? "loading"}`;
  observations.push(text);
  return <div><p>{text}</p><p>Dashboard: {history.data ?? "loading"}</p></div>;
}
function Controls() {
  const auth = useAuth();
  return <><button onClick={() => void auth.login("A", "unused")}>Login A</button>
    <button onClick={() => void auth.login("B", "unused")}>Login B</button>
    <button onClick={() => void auth.logout().catch(() => undefined)}>Logout</button>
    <button onClick={() => void auth.refreshUser()}>Restore</button>
    {auth.user ? <PrivateData /> : <p>Signed out</p>}</>;
}
function setup() {
  const publicClient = new QueryClient();
  publicClient.setQueryData(["public"], "keep me");
  render(<QueryClientProvider client={publicClient}><AuthProvider><AccountQueryProvider><Controls /></AccountQueryProvider></AuthProvider></QueryClientProvider>);
  return publicClient;
}
describe("account private query boundary", () => {
  beforeEach(() => {
    observations.length = 0;
    api.restoreSession.mockReset().mockRejectedValue(new Error("signed out"));
    api.login.mockReset().mockImplementation(async (id: string) => ({ user: account(id) }));
    api.logout.mockReset().mockResolvedValue(undefined);
  });
  it.each([false, true])("isolates history, progress and dashboard after logout (failure=%s)", async (fails) => {
    if (fails) api.logout.mockRejectedValue(new Error("offline"));
    const global = setup();
    const user = userEvent.setup();
    await user.click(screen.getByText("Login A"));
    await screen.findByText("A: A history / A progress");
    await user.click(screen.getByText("Logout"));
    await screen.findByText("Signed out");
    await user.click(screen.getByText("Login B"));
    await screen.findByText("B: B history / B progress");
    expect(observations.filter(row => row.startsWith("B:")).every(row => !row.includes("A history") && !row.includes("A progress"))).toBe(true);
    expect(screen.getByText("Dashboard: B history")).toBeInTheDocument();
    expect(global.getQueryData(["public"])).toBe("keep me");
  });
  it("isolates a restored different account and preserves same-account refresh", async () => {
    api.restoreSession.mockResolvedValue(account("A"));
    setup();
    await screen.findByText("A: A history / A progress");
    const user = userEvent.setup();
    await user.click(screen.getByText("Restore"));
    expect(screen.getByText("A: A history / A progress")).toBeInTheDocument();
    api.restoreSession.mockResolvedValue(account("B"));
    await user.click(screen.getByText("Restore"));
    await waitFor(() => expect(screen.getByText("B: B history / B progress")).toBeInTheDocument());
    expect(observations.filter(row => row.startsWith("B:")).every(row => !row.includes("A history") && !row.includes("A progress"))).toBe(true);
  });
});
