import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

export function renderWithQueryClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });

  return {
    queryClient,
    ...render(<QueryWrapper client={queryClient}>{ui}</QueryWrapper>),
  };
}

function QueryWrapper({
  children,
  client,
}: {
  children: ReactNode;
  client: QueryClient;
}) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
