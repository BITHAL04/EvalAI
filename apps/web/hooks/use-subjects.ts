"use client";

import { useApiQuery } from "@/lib/api";
import type { Page, Subject } from "@/types/api";

export const useSubjects = () => useApiQuery<Page<Subject>>(["subjects"], "/subjects?limit=100");
