import { redirect } from "next/navigation";

import { landingAuthHref } from "@/lib/auth-redirect";

export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const params = await searchParams;
  redirect(landingAuthHref("signup", typeof params.next === "string" ? params.next : null));
}
