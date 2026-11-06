"use client";

import { useApiQuery } from "@/lib/api";
import type { Me } from "@/types/api";

export function useMe() {
  return useApiQuery<Me>(["me"], "/users/me", { staleTime: 60_000, retry: false });
}
