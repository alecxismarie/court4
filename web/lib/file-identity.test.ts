import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { fileIdentity } from "@/lib/file-identity";

describe("reselected file identity", () => {
  it("hashes every byte using the server's fixed chunk commitment", async () => {
    const data = Buffer.concat([Buffer.alloc(8_388_608, "x"), Buffer.from("last")]);
    const root = createHash("sha256").update("court4-file-v1\n")
      .update(createHash("sha256").update(data.subarray(0, 8_388_608)).digest())
      .update(createHash("sha256").update("last").digest()).update("\n8388612").digest("hex");
    const original = new File([data], "match.mp4");
    expect(await fileIdentity(original)).toBe(`sha256-chunks-v1:${root}`);
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
