import { ManualCalibrationWorkspace } from "@/components/manual-calibration-workspace";

export default function ManualCalibrationPage({
  params,
}: {
  params: { analysisId: string };
}) {
  return (
    <div className="mx-auto max-w-7xl">
      <ManualCalibrationWorkspace analysisId={params.analysisId} />
    </div>
  );
}
