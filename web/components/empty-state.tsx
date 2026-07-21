import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-md border border-dashed border-court-line bg-white p-8 text-center">
      <h2 className="text-lg font-semibold text-court-ink">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-court-muted">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
