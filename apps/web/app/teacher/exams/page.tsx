"use client";

import Link from "next/link";
import { useState } from "react";
import { Button, EmptyState, ErrorState, LoadingBlock, PageHeader, SampleBadge, Select, StatusBadge, Table, Td } from "@/components/ui";
import { useApiQuery } from "@/lib/api";
import { fmtDate } from "@/lib/utils";
import type { Exam, Page } from "@/types/api";

const FILTERS = [["", "All"], ["draft", "Draft"], ["review", "In review"], ["published", "Published"], ["closed", "Closed"], ["results_published", "Results out"]];

export default function Exams() {
  const [status, setStatus] = useState("");
  const q = useApiQuery<Page<Exam>>(["exams", status], `/examinations?limit=100${status ? `&status=${status}` : ""}`, { refetchInterval: (x) => (x.state.data?.items.some((e) => e.status === "generating") ? 4000 : false) });
  return (
    <>
      <PageHeader title="Examinations" actions={<><Select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-44">{FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select><Button asChild><Link href="/teacher/exams/new">Create examination</Link></Button></>} />
      {q.isLoading ? <LoadingBlock /> : q.error ? <ErrorState error={q.error} retry={q.refetch} /> : !q.data!.items.length ? (
        <EmptyState title={status ? "No examinations with this status" : "No examinations yet"} action={<Button asChild><Link href="/teacher/exams/new">Create examination</Link></Button>} />
      ) : (
        <Table head={["Examination", "Subject", "Marks", "Submissions", "Status", "Created"]}>
          {q.data!.items.map((e) => (
            <tr key={e.id} className="hover:bg-canvas/50">
              <Td><Link href={`/teacher/exams/${e.id}`} className="font-medium hover:text-primary">{e.title}</Link></Td>
              <Td>{e.subject}</Td>
              <Td className="tabular-nums">{e.total_marks}</Td>
              <Td className="tabular-nums">{e.submissions ?? 0}</Td>
              <Td><div className="flex gap-1.5"><StatusBadge status={e.status} />{e.is_demo && <SampleBadge />}</div></Td>
              <Td className="whitespace-nowrap text-muted">{fmtDate(e.created_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
