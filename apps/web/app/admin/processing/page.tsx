"use client";

import { Card, ErrorState, LoadingBlock, PageHeader, Stat, StatusBadge, Table, Td } from "@/components/ui";
import { useApiQuery } from "@/lib/api";
import { fmtDate, label } from "@/lib/utils";

type J = { counts: Record<string, number>; recent: { id: string; type: string; status: string; attempts: number; error: string | null; created_at: string }[] };

export default function Processing() {
  const q = useApiQuery<J>(["jobs"], "/analytics/jobs", { refetchInterval: 5000 });
  if (q.isLoading) return <LoadingBlock />;
  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />;
  const d = q.data!;
  return (
    <>
      <PageHeader title="AI processing" description="Background work: indexing documents, generating papers, reading answer sheets, evaluating and reviewing challenges. Jobs survive restarts and retry automatically." />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">{Object.entries(d.counts).map(([k, v]) => <Stat key={k} label={label(k)} value={v} />)}</div>
      <h2 className="mb-3 mt-8 font-semibold">Recent jobs</h2>
      {!d.recent.length ? <Card className="p-5 text-sm text-muted">No jobs yet.</Card> : (
        <Table head={["Job", "Status", "Attempts", "Created", "Error"]}>
          {d.recent.map((j) => <tr key={j.id}><Td>{label(j.type)}</Td><Td><StatusBadge status={j.status} /></Td><Td className="tabular-nums">{j.attempts}</Td><Td className="whitespace-nowrap text-muted">{fmtDate(j.created_at)}</Td><Td className="max-w-md text-xs text-mark">{j.error}</Td></tr>)}
        </Table>
      )}
    </>
  );
}
