import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { emptyPlayerProfile, savePlayerProfile } from "@/lib/player-profile";
import { usePlayerProfile } from "@/lib/use-player-profile";

const authMock = vi.hoisted(() => vi.fn());
const playerOneId = "56ae6283-69ee-44b6-9f19-6bf9dc1d7092";
const playerTwoId = "57bd7394-70ff-45c7-8a20-7ca0ed2e8103";

vi.mock("@/lib/auth-context", () => ({
  useOptionalAuth: authMock,
}));

describe("account-scoped player profile hook", () => {
  beforeEach(() => {
    window.localStorage.clear();
    authMock.mockReturnValue({ user: { id: playerOneId } });
  });

  it("loads separate profiles and never renders the previous account after a switch", async () => {
    savePlayerProfile(playerOneId, {
      ...emptyPlayerProfile,
      displayName: "Alexis",
      profileImageDataUrl: "data:image/png;base64,AQID",
    });
    savePlayerProfile(playerTwoId, {
      ...emptyPlayerProfile,
      displayName: "Mimi",
    });

    const view = render(<ProfileProbe />);
    expect(await screen.findByText("Alexis:photo")).toBeInTheDocument();

    authMock.mockReturnValue({ user: { id: playerTwoId } });
    view.rerender(<ProfileProbe />);

    expect(screen.queryByText("Alexis:photo")).not.toBeInTheDocument();
    expect(await screen.findByText("Mimi:no-photo")).toBeInTheDocument();
  });

  it("hydrates the persisted onboarding name on a new browser", async () => {
    authMock.mockReturnValue({ user: { id: playerOneId, display_name: "Alexis" } });

    render(<ProfileProbe />);

    expect(await screen.findByText("Alexis:no-photo")).toBeInTheDocument();
    expect(window.localStorage).toHaveLength(0);
  });
});

function ProfileProbe() {
  const { profile, isLoaded } = usePlayerProfile();
  if (!isLoaded) return <p>Loading profile</p>;
  return (
    <p>
      {profile.displayName || "No name"}:{profile.profileImageDataUrl ? "photo" : "no-photo"}
    </p>
  );
}
