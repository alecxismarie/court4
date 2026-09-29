import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthenticatedImage } from "@/components/authenticated-image";
import { loadArtifactImage } from "@/lib/artifact-image-loader";
import { AccountQueryProvider } from "@/lib/account-query-provider";
import { Activity } from "react";

vi.mock("@/lib/artifact-image-loader", () => ({ loadArtifactImage: vi.fn() }));
const auth = vi.hoisted(() => ({ user: { id: "A" } }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => auth }));
const load = vi.mocked(loadArtifactImage);
const createUrl = vi.fn();
const revokeUrl = vi.fn();

describe("private artifact images", () => {
  beforeEach(() => {
    auth.user = { id: "A" };
    load.mockReset(); createUrl.mockReset().mockReturnValue("blob:private-image"); revokeUrl.mockReset();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeUrl });
  });
  afterEach(cleanup);

  it("never places a private URL in img src and revokes its blob on unmount", async () => {
    let resolve!: (blob: Blob) => void;
    load.mockImplementation(() => new Promise(done => { resolve = done; }));
    const view = render(<AuthenticatedImage src="https://api.test/private.jpg" alt="Private preview" />);
    expect(screen.getByRole("img")).not.toHaveAttribute("src");
    expect(load).toHaveBeenCalledWith("https://api.test/private.jpg", expect.any(AbortSignal));
    await act(async () => resolve(new Blob(["image"])));
    expect(screen.getByRole("img")).toHaveAttribute("src", "blob:private-image");
    view.unmount();
    expect(revokeUrl).toHaveBeenCalledWith("blob:private-image");
    expect(load.mock.calls[0][1].aborted).toBe(true);
  });

  it("aborts stale sources and never creates a blob from a late old-account response", async () => {
    let oldResponse!: (blob: Blob) => void;
    load.mockImplementationOnce(() => new Promise(done => { oldResponse = done; }))
      .mockResolvedValueOnce(new Blob(["account B"]));
    const view = render(<AuthenticatedImage src="/account-a/image" alt="Preview" />);
    view.rerender(<AuthenticatedImage src="/account-b/image" alt="Preview" />);
    expect(load.mock.calls[0][1].aborted).toBe(true);
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "blob:private-image"));
    await act(async () => oldResponse(new Blob(["account A"])));
    expect(createUrl).toHaveBeenCalledTimes(1);
  });

  it("removes and revokes the old blob immediately when the source changes", async () => {
    load.mockResolvedValueOnce(new Blob(["first"])).mockImplementationOnce(() => new Promise(() => {}));
    const view = render(<AuthenticatedImage src="/first" alt="Preview" />);
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "blob:private-image"));
    view.rerender(<AuthenticatedImage src="/second" alt="Preview" />);
    expect(screen.getByRole("img")).not.toHaveAttribute("src");
    expect(revokeUrl).toHaveBeenCalledWith("blob:private-image");
  });

  it("preserves the error callback after final failure without a network fallback", async () => {
    load.mockRejectedValue(new Error("Unavailable"));
    const error = vi.fn();
    render(<AuthenticatedImage src="/private" alt="Preview" onError={error} />);
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "data:image/png;base64,"));
    fireEvent.error(screen.getByRole("img"));
    expect(error).toHaveBeenCalledTimes(1);
  });

  it("does not reuse a same-URL blob across the existing account identity boundary", async () => {
    load.mockResolvedValueOnce(new Blob(["account A"])).mockResolvedValueOnce(new Blob(["account B"]));
    createUrl.mockReturnValueOnce("blob:account-a").mockReturnValueOnce("blob:account-b");
    const content = <AccountQueryProvider><AuthenticatedImage src="/private/same-path" alt="Preview" /></AccountQueryProvider>;
    const view = render(content);
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "blob:account-a"));
    auth.user = { id: "B" };
    view.rerender(<AccountQueryProvider><AuthenticatedImage src="/private/same-path" alt="Preview" /></AccountQueryProvider>);
    expect(screen.getByRole("img")).not.toHaveAttribute("src");
    expect(revokeUrl).toHaveBeenCalledWith("blob:account-a");
    expect(load.mock.calls[0][1].aborted).toBe(true);
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "blob:account-b"));
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("does not retain revoked blob URLs when a cached view is hidden and restored", async () => {
    load.mockResolvedValueOnce(new Blob(["first"])).mockResolvedValueOnce(new Blob(["restored"]));
    createUrl.mockReturnValueOnce("blob:first").mockReturnValueOnce("blob:restored");
    const view = render(<Activity mode="visible"><AuthenticatedImage src="/private" alt="Preview" /></Activity>);
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "blob:first"));
    view.rerender(<Activity mode="hidden"><AuthenticatedImage src="/private" alt="Preview" /></Activity>);
    expect(revokeUrl).toHaveBeenCalledWith("blob:first");
    view.rerender(<Activity mode="visible"><AuthenticatedImage src="/private" alt="Preview" /></Activity>);
    expect(screen.getByRole("img")).not.toHaveAttribute("src", "blob:first");
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "blob:restored"));
  });
});
