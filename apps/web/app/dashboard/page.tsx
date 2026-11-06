"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthNotConfigured } from "@/components/config-error";
import { Logo } from "@/components/logo";
import { Button, ErrorState } from "@/components/ui";
import { ApiError, INSTITUTION_KEY, useApi } from "@/lib/api";
import { useSession } from "@/lib/auth";
import { AUTH_MODE } from "@/lib/config";
import type { Me } from "@/types/api";

/** Landing point after sign-in: sync the profile from the verified token, then route by role. */
export default function Dashboard() {
  const api = useApi();
  const router = useRouter();
  const qc = useQueryClient();
  const { ready, signedIn, signOut } = useSession();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!ready) return;
    if (!signedIn) { router.replace("/sign-in"); return; }
    api<Me>("/users/sync", { method: "POST" }).then((m) => {
      qc.setQueryData(["me"], m);
      setMe(m);
      if (!m.memberships.length) return;
      let inst = m.memberships[0];
      try { inst = m.memberships.find((x) => x.institution_id === localStorage.getItem(INSTITUTION_KEY)) ?? inst; localStorage.setItem(INSTITUTION_KEY, inst.institution_id); } catch {}
      router.replace(`/${inst.role}`);
    }).catch(setError);
  }, [ready, signedIn, api, router, qc]);

  if (AUTH_MODE === "none") return <AuthNotConfigured />;
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-4">
      <Logo />
      {error ? <ErrorState error={error} retry={() => window.location.reload()} /> : me && !me.memberships.length ? (
        <div className="rounded-[var(--radius-card)] border border-line bg-paper p-6">
          <h1 className="text-lg font-semibold">You are signed in as {me.email}</h1>
          <p className="mt-2 text-sm text-muted">This account is not part of an institution yet. Ask your administrator to invite this email address, then sign in again.</p>
          <Button className="mt-4" variant="secondary" onClick={() => signOut()}>Sign out</Button>
        </div>
      ) : (
        <p className="flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Setting up your workspace…</p>
      )}
    </main>
  );
}
