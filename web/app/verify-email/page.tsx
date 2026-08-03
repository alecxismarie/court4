import { VerifyEmail } from "@/components/email-verification";

export default function VerifyEmailPage({
  searchParams,
}: {
  searchParams: { token?: string };
}) {
  return <VerifyEmail token={searchParams.token ?? ""} />;
}
