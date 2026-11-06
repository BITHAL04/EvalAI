"use client";

import Link from "next/link";
import { EmptyState, ErrorState, LoadingBlock, Marks, PageHeader, SampleBadge, Table, Td } from "@/components/ui";
import { useApiQuery } from "@/lib/api";
import { fmtDate } from "@/lib/utils";

type R = { examination_id: string; examination: string; subject: string; total_marks: number; max_marks: number; percentage: number; published_at: string; is_demo: boolean };

export default function Results() {
  const q = useApiQuery<{ items: R[] }>(["results"], "/results");
  return (
    <>
      <PageHeader title="Results" description="Marks approved and published by your teachers." />
      {q.isLoading ? <LoadingBlock /> : q.error ? <ErrorState error={q.error} retry={q.refetch} /> : !q.data!.items.length ? <EmptyState title="No results yet" body="Results appear here once your teacher publishes them." /> : (
        <Table head={["Examination", "Subject", "Marks", "Percentage", "Published"]}>
          {q.data!.items.map((r) => (
            <tr key={r.examination_id} className="hover:bg-canvas/50">
              <Td><Link href={`/student/results/${r.examination_id}`} className="font-medium hover:text-primary">{r.examination}</Link> {r.is_demo && <SampleBadge />}</Td>
              <Td>{r.subject}</Td>
              <Td><Marks got={r.total_marks} max={r.max_marks} /></Td>
              <Td className="tabular-nums">{r.percentage}%</Td>
              <Td className="whitespace-nowrap text-muted">{fmtDate(r.published_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
