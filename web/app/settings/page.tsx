import { Settings } from "lucide-react";
import Link from "next/link";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Settings
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-court-ink">Application settings</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-court-muted">
          Settings are reserved for application and technical preferences. Sports identity
          and player preferences live on the Player page.
        </p>
      </section>

      <section className="rounded-md border border-court-line bg-white p-5 shadow-panel">
        <div className="flex gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-court-panel text-court-green">
            <Settings aria-hidden="true" className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-court-ink">Profile boundary</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-court-muted">
              Use <Link href="/player" className="font-semibold text-court-green">Player</Link>{" "}
              for display name, dominant hand, experience level, and local club labels.
              This page will hold app-level preferences as Court4 grows.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
