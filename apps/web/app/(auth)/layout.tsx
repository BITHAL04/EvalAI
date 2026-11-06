import type { ReactNode } from "react";
import { Logo } from "@/components/logo";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-canvas px-4 py-10">
      <Logo />
      {children}
    </main>
  );
}
