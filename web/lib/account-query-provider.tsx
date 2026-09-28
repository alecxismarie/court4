"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";

// Swap the entire private cache in the same render as identity changes. An
// effect-only reset could expose the previous user's fresh data for one render.
// The outer provider's public cache is deliberately left intact.
export function AccountQueryProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return user ? <PrivateQueries key={user.id}>{children}</PrivateQueries> : children;
}

function PrivateQueries({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { retry: 1, staleTime: 15_000 } },
  }));
  useEffect(() => () => { client.clear(); }, [client]);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
