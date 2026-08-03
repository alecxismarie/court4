import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ShareCardPanel } from "@/components/share-card-panel";
import { savePlayerProfile } from "@/lib/player-profile";
import { createShareCardPng, renderShareCardToCanvas } from "@/lib/share-card-renderer";
import { makeAnalyticsReport, makeMatchIQReport } from "@/test/factories";
import { renderWithQueryClient } from "@/test/render";

vi.mock("@/lib/share-card-renderer", () => ({
  renderShareCardToCanvas: vi.fn(async () => undefined),
  createShareCardPng: vi.fn(async () => new Blob(["png"], { type: "image/png" })),
}));

const mockedRenderShareCardToCanvas = vi.mocked(renderShareCardToCanvas);
const mockedCreateShareCardPng = vi.mocked(createShareCardPng);
const authUserId = vi.hoisted(() => "56ae6283-69ee-44b6-9f19-6bf9dc1d7092");

vi.mock("@/lib/auth-context", () => ({
  useOptionalAuth: () => ({ user: { id: authUserId } }),
}));

describe("share card panel", () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockedRenderShareCardToCanvas.mockClear();
    mockedCreateShareCardPng.mockClear();
    Object.defineProperty(navigator, "share", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(navigator, "canShare", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:court4-share-card"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(() => undefined),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders card controls and updates the preview data from user choices", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(
      <ShareCardPanel report={makeAnalyticsReport()} matchIQ={makeMatchIQReport()} />,
    );

    expect(screen.getByText("Share Performance Card")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Story/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await user.clear(screen.getByLabelText("Display name"));
    await user.type(screen.getByLabelText("Display name"), "Ava");
    await user.selectOptions(screen.getByLabelText("Movement image"), "trajectory");

    await waitFor(() => {
      const latestCall = mockedRenderShareCardToCanvas.mock.calls.at(-1);
      expect(latestCall?.[1]).toMatchObject({
        playerName: "Ava",
        artifactLabel: "Trajectory",
      });
    });
  });

  it("creates a PNG download for the selected format", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(
      <ShareCardPanel report={makeAnalyticsReport()} matchIQ={makeMatchIQReport()} />,
    );

    await user.click(screen.getByRole("button", { name: /Portrait/ }));
    await user.click(screen.getByRole("button", { name: /Download PNG/ }));

    await waitFor(() => expect(mockedCreateShareCardPng).toHaveBeenCalled());
    expect(mockedCreateShareCardPng.mock.calls.at(-1)?.[1]).toMatchObject({
      id: "portrait",
      width: 1080,
      height: 1350,
    });
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
    expect(await screen.findByText("PNG downloaded.")).toBeInTheDocument();
  });

  it("uses the saved player profile as the default display name", async () => {
    savePlayerProfile(authUserId, {
      displayName: "Ava",
      dominantHand: "right",
      experienceLevel: "advanced",
      homeClub: "",
      profileImageDataUrl: "",
    });

    renderWithQueryClient(
      <ShareCardPanel report={makeAnalyticsReport()} matchIQ={makeMatchIQReport()} />,
    );

    expect(await screen.findByDisplayValue("Ava")).toBeInTheDocument();
    await waitFor(() => {
      const latestCall = mockedRenderShareCardToCanvas.mock.calls.at(-1);
      expect(latestCall?.[1]).toMatchObject({ playerName: "Ava" });
    });
  });

  it("uses native file sharing when the browser supports it", async () => {
    const user = userEvent.setup();
    const share = vi.fn(async (_data?: ShareData) => undefined);
    Object.defineProperty(navigator, "share", {
      configurable: true,
      value: share,
    });
    Object.defineProperty(navigator, "canShare", {
      configurable: true,
      value: vi.fn(() => true),
    });

    renderWithQueryClient(
      <ShareCardPanel report={makeAnalyticsReport()} matchIQ={makeMatchIQReport()} />,
    );

    await user.click(screen.getByRole("button", { name: "Share" }));

    await waitFor(() => expect(share).toHaveBeenCalled());
    const firstSharePayload = share.mock.calls[0]?.[0];
    expect(firstSharePayload).toMatchObject({
      title: "Court4 Performance Card",
      text: "Local Player Court4 movement results",
    });
    expect(firstSharePayload?.files).toHaveLength(1);
    expect(await screen.findByText("Native share opened.")).toBeInTheDocument();
  });
});
