import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...v: ClassValue[]) => twMerge(clsx(v));

export const fmtMarks = (n: number | null | undefined) => (n === null || n === undefined ? "–" : Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0$/, ""));

export const fmtDate = (s?: string | null) =>
  s ? new Date(s).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "–";

export const pct = (a: number, b: number) => (b ? Math.round((a / b) * 1000) / 10 : 0);

export const label = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export function bytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}
