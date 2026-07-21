import { AnalyticsDetails } from "@/components/analytics-details";

export default function AnalyticsPage({
  params,
}: {
  params: { analysisId: string };
}) {
  return <AnalyticsDetails analysisId={params.analysisId} />;
}
