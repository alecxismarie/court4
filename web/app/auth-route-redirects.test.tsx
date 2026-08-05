import { beforeEach, describe, expect, it, vi } from "vitest";

const redirect = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ redirect }));

import LoginPage from "@/app/login/page";
import RegisterPage from "@/app/register/page";

describe("legacy auth route consolidation", () => {
  beforeEach(() => redirect.mockReset());

  it("redirects login to the landing login tab and preserves a safe next route", async () => {
    await LoginPage({ searchParams: Promise.resolve({ next: "/upload-match" }) });

    expect(redirect).toHaveBeenCalledWith("/?auth=login&next=%2Fupload-match");
  });

  it("redirects register to the landing signup tab", async () => {
    await RegisterPage({ searchParams: Promise.resolve({}) });

    expect(redirect).toHaveBeenCalledWith("/?auth=signup");
  });

  it("drops external and auth-loop next destinations", async () => {
    await LoginPage({
      searchParams: Promise.resolve({ next: "https://malicious.example" }),
    });
    await RegisterPage({ searchParams: Promise.resolve({ next: "/login" }) });

    expect(redirect).toHaveBeenNthCalledWith(1, "/?auth=login");
    expect(redirect).toHaveBeenNthCalledWith(2, "/?auth=signup");
  });
});
