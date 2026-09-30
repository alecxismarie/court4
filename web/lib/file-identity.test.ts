import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import { fileIdentity } from "@/lib/file-identity";

describe("reselected file identity", () => {
  it("hashes every byte using the server's fixed chunk commitment", async () => {
    const data = Buffer.concat([Buffer.alloc(8_388_608, "x"), Buffer.from("last")]);
    const root = createHash("sha256").update("court4-file-v1\n")
      .update(createHash("sha256").update(data.subarray(0, 8_388_608)).digest())
      .update(createHash("sha256").update("last").digest()).update("\n8388612").digest("hex");
    const original = new File([data], "match.mp4");
    const onChunk = vi.fn();
    expect(await fileIdentity(original, undefined, onChunk)).toBe(`sha256-chunks-v1:${root}`);
    expect(onChunk).toHaveBeenCalledTimes(2);
    expect(await fileIdentity(new File([data], "renamed.mp4"))).toBe(await fileIdentity(original));
    data[data.length - 1] = 33;
    expect(await fileIdentity(new File([data], "match.mp4"))).not.toBe(`sha256-chunks-v1:${root}`);
  });

  it("allows a user to interrupt a file check", async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(fileIdentity(new File(["abc"], "match.mp4"), controller.signal))
      .rejects.toMatchObject({ name: "AbortError" });
  });
});
