"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth";
import type { ApiError } from "@/lib/api";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: (n, e) => n < 2 && ((e as ApiError).status ?? 500) >= 500 } },
  }));
  return (
    <AuthProvider>
      <QueryClientProvider client={client}>
        {children}
        <Toaster position="bottom-right" richColors closeButton />
      </QueryClientProvider>
    </AuthProvider>
  );
}
