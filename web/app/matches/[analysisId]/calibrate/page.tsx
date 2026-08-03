import { ManualCalibrationWorkspace } from "@/components/manual-calibration-workspace";

export default async function ManualCalibrationPage({
  params,
}: {
  params: Promise<{ analysisId: string }>;
}) {
  const { analysisId } = await params;
  return (
    <div className="mx-auto max-w-7xl">
      <ManualCalibrationWorkspace analysisId={analysisId} />
    </div>
  );
}
