import Link from "next/link";
import type { ReactNode } from "react";

export function LegalDocument({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="mx-auto min-h-screen max-w-3xl px-5 py-12 text-court-ink">
      <Link href="/" className="font-semibold text-court-green underline">Back to Court4</Link>
      <p className="mt-8 text-sm font-semibold uppercase tracking-wide text-court-green">
        Private-alpha draft — legal review pending
      </p>
      <h1 className="mt-2 text-4xl font-bold">{title}</h1>
      <p className="mt-3 text-sm text-court-muted">Effective draft: August 3, 2026</p>
      <article className="mt-8 space-y-6">{children}</article>
    </main>
  );
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-2xl font-semibold">{title}</h2>
      <div className="mt-2 space-y-3 leading-7 text-court-muted">{children}</div>
    </section>
  );
}
