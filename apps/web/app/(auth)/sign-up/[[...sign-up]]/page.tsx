"use client";

import { SignUp } from "@clerk/nextjs";
import { AuthNotConfigured } from "@/components/config-error";
import { AUTH_MODE } from "@/lib/config";

export default function Page() {
  if (AUTH_MODE !== "clerk") return <AuthNotConfigured />;
  return <SignUp />;
}
