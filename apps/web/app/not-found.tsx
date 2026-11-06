import Link from "next/link";
import { Logo } from "@/components/logo";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-4">
      <Logo />
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-muted">The link may be out of date, or you may not have access to this record.</p>
      <Link href="/dashboard" className="text-primary hover:underline">Go to your dashboard</Link>
    </main>
  );
}
