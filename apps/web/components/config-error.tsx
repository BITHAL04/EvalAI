import { KeyRound } from "lucide-react";
import { Logo } from "./logo";

export function AuthNotConfigured() {
  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-4">
      <Logo />
      <div className="mt-8 rounded-[var(--radius-card)] border border-line bg-paper p-6">
        <KeyRound className="h-5 w-5 text-warning" aria-hidden />
        <h1 className="mt-3 text-lg font-semibold">Sign-in is not configured</h1>
        <p className="mt-2 text-sm text-muted">
          Set <code className="rounded bg-canvas px-1">NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY</code> and <code className="rounded bg-canvas px-1">CLERK_SECRET_KEY</code> for this deployment,
          then rebuild. Setup steps are in <code className="rounded bg-canvas px-1">docs/DEPLOYMENT.md</code>.
        </p>
      </div>
    </main>
  );
}
