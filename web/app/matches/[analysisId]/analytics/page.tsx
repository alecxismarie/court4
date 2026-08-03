import { AnalyticsDetails } from "@/components/analytics-details";

export default async function AnalyticsPage({
  params,
}: {
  params: Promise<{ analysisId: string }>;
}) {
  const { analysisId } = await params;
  return <AnalyticsDetails analysisId={analysisId} />;
}
