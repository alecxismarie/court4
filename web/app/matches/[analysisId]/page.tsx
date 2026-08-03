import { MatchDetails } from "@/components/match-details";

export default async function MatchDetailsPage({
  params,
}: {
  params: Promise<{ analysisId: string }>;
}) {
  const { analysisId } = await params;
  return <MatchDetails analysisId={analysisId} />;
}
