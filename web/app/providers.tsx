"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, Suspense, useState } from "react";

import { AuthGate } from "@/components/auth-gate";
import { AuthProvider } from "@/lib/auth-context";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            staleTime: 15_000,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Suspense
          fallback={
            <main className="grid min-h-screen place-items-center text-court-muted">
              Loading…
            </main>
          }
        >
          <AuthGate>{children}</AuthGate>
        </Suspense>
      </AuthProvider>
    </QueryClientProvider>
  );
}
