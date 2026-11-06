import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "@/components/providers";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: { default: "EvalAI — Understand. Evaluate. Improve.", template: "%s · EvalAI" },
  description: "AI question papers, handwritten answer evaluation against approved rubrics, and teacher-reviewed results.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body><Providers>{children}</Providers></body>
    </html>
  );
}
