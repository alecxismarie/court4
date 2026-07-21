import { MatchDetails } from "@/components/match-details";

export default function MatchDetailsPage({
  params,
}: {
  params: { analysisId: string };
}) {
  return <MatchDetails analysisId={params.analysisId} />;
}
