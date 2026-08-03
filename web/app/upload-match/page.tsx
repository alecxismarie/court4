"use client";

import Link from "next/link";

import { UploadDropzone } from "@/components/upload-dropzone";
import { useAuth } from "@/lib/auth-context";

export default function UploadMatchPage() {
  const { user } = useAuth();

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {user?.email_verified_at ? (
        <UploadDropzone />
      ) : (
        <section className="rounded-md border border-amber-200 bg-amber-50 p-6">
          <h1 className="text-2xl font-semibold text-court-ink">Verify your email to upload</h1>
          <p className="mt-3 text-sm leading-6 text-court-muted">
            You can continue using your Court4 account, but match uploads and re-analysis
            stay locked until your email is confirmed.
          </p>
          <Link
            href="/verification-pending"
            className="mt-5 inline-block rounded-md bg-court-navy px-4 py-2 font-semibold text-white"
          >
            Verify email
          </Link>
        </section>
      )}
    </div>
  );
}
