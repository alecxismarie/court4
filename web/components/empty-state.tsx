import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-md border border-dashed border-court-line bg-white p-8 text-center",
        className,
      )}
    >
      <h2 className="text-lg font-semibold text-court-ink">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-court-muted">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
