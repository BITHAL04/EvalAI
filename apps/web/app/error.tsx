"use client";

import { Button } from "@/components/ui";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col justify-center gap-3 px-4">
      <h1 className="text-xl font-semibold">This page failed to load</h1>
      <p className="text-sm text-muted">Reload to try again. If it keeps happening, the API may be unavailable.</p>
      <Button className="self-start" onClick={reset}>Reload</Button>
    </main>
  );
}
