import Link from "next/link";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="inline-flex items-center gap-2 font-semibold tracking-tight" aria-label="EvalAI home">
      <svg viewBox="0 0 28 28" className="h-7 w-7" aria-hidden>
        <rect width="28" height="28" rx="7" fill="var(--color-primary)" />
        <path d="M8 14.5l4 4 8-9" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="21.5" cy="21" r="2.4" fill="var(--color-mark)" />
      </svg>
      <span className="text-[17px]">EvalAI</span>
    </Link>
  );
}
