import { redirect } from "next/navigation";

import { landingAuthHref } from "@/lib/auth-redirect";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const params = await searchParams;
  redirect(landingAuthHref("login", typeof params.next === "string" ? params.next : null));
}
