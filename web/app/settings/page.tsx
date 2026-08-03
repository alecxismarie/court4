import { AccountSecurity } from "@/components/account-security";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <section className="rounded-md border border-court-line bg-white p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
          Settings
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-court-ink">Account security</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-court-muted">
          Manage your verified email, password, and signed-in browsers.
        </p>
      </section>

      <AccountSecurity />
    </div>
  );
}
