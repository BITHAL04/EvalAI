"use client";

import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { useState } from "react";
import { useApiQuery } from "@/lib/api";
import { Button, Card, ErrorState, Skeleton } from "./ui";

/** Original page scans. Always available to whoever is reviewing marks. */
export function PageViewer({ submissionId, focus }: { submissionId: string; focus?: number }) {
  const q = useApiQuery<{ items: { page_number: number; url: string }[] }>(["pages", submissionId], `/submissions/${submissionId}/pages`, { staleTime: 4 * 60_000 });
  // The requested page wins until the reviewer navigates; a new request resets it.
  const [sel, setSel] = useState<{ focus?: number; page: number }>({ focus, page: focus ?? 1 });
  const page = sel.focus === focus ? sel.page : focus ?? 1;
  const setPage = (p: number) => setSel({ focus, page: p });
  const [zoom, setZoom] = useState(1);
  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />;
  const items = q.data?.items ?? [];
  const cur = items.find((p) => p.page_number === page);
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-3 py-2 text-sm">
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft className="h-4 w-4" /></Button>
          <span className="tabular-nums">Page {page} of {items.length || "–"}</span>
          <Button size="icon" variant="ghost" aria-label="Next page" disabled={page >= items.length} onClick={() => setPage(page + 1)}><ChevronRight className="h-4 w-4" /></Button>
        </div>
        <div className="flex gap-1">
          <Button size="icon" variant="ghost" aria-label="Zoom out" disabled={zoom <= 1} onClick={() => setZoom(zoom - 0.5)}><ZoomOut className="h-4 w-4" /></Button>
          <Button size="icon" variant="ghost" aria-label="Zoom in" disabled={zoom >= 3} onClick={() => setZoom(zoom + 0.5)}><ZoomIn className="h-4 w-4" /></Button>
        </div>
      </div>
      <div className="max-h-[75vh] overflow-auto bg-canvas">
        {q.isLoading ? <Skeleton className="m-4 h-[60vh]" /> : cur ? (
          // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL, not optimisable
          <img src={cur.url} alt={`Answer sheet page ${page}`} style={{ width: `${zoom * 100}%`, maxWidth: "none" }} className="block" />
        ) : <p className="p-6 text-sm text-muted">No page images.</p>}
      </div>
    </Card>
  );
}
