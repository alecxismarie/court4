import { CircleCheck, CircleDashed, CircleX, Clock3 } from "lucide-react";

import type { AnalysisHistoryItem } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function AnalysisStatusBadge({ status }: { status: AnalysisHistoryItem["status"] }) {
  const label = {
    PROCESSING: "Processing",
    READY: "Ready",
    LIMITED: "Limited evidence",
    UNSUITABLE: "Unsuitable recording",
    FAILED: "Failed",
    LEGACY: "Legacy analysis",
  }[status];
  const Icon =
    status === "READY"
      ? CircleCheck
      : status === "PROCESSING"
        ? Clock3
        : status === "FAILED" || status === "UNSUITABLE"
          ? CircleX
          : CircleDashed;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-semibold",
        status === "READY" && "border-green-200 bg-green-50 text-court-green",
        status === "PROCESSING" && "border-blue-200 bg-blue-50 text-blue-800",
        (status === "LIMITED" || status === "LEGACY") &&
          "border-amber-200 bg-amber-50 text-amber-900",
        (status === "FAILED" || status === "UNSUITABLE") &&
          "border-red-200 bg-red-50 text-red-800",
      )}
    >
      <Icon aria-hidden="true" className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}

export function ContributionBadge({
  status,
}: {
  status: AnalysisHistoryItem["contribution"]["status"];
}) {
  const label = {
    INCLUDED: "Included in Play History",
    EXCLUDED: "Excluded from Play History",
    PROVISIONAL: "Provisional",
    NOT_EVALUATED: "Not yet evaluated",
  }[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-semibold",
        status === "INCLUDED" && "border-green-200 bg-green-50 text-court-green",
        status === "EXCLUDED" && "border-red-200 bg-red-50 text-red-800",
        (status === "PROVISIONAL" || status === "NOT_EVALUATED") &&
          "border-amber-200 bg-amber-50 text-amber-900",
      )}
    >
      {status === "INCLUDED" ? (
        <CircleCheck aria-hidden="true" className="h-3.5 w-3.5" />
      ) : status === "EXCLUDED" ? (
        <CircleX aria-hidden="true" className="h-3.5 w-3.5" />
      ) : (
        <CircleDashed aria-hidden="true" className="h-3.5 w-3.5" />
      )}
      {label}
    </span>
  );
}
