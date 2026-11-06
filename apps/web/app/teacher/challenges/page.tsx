"use client";

import Link from "next/link";
import { useState } from "react";
import { EmptyState, ErrorState, LoadingBlock, Marks, PageHeader, Select, StatusBadge, Table, Td } from "@/components/ui";
import { useApiQuery } from "@/lib/api";
import { fmtDate, label } from "@/lib/utils";
import type { Challenge, Page } from "@/types/api";

export default function Challenges() {
  const [status, setStatus] = useState("pending_teacher_review");
  const q = useApiQuery<Page<Challenge>>(["challenges", status], `/challenges?limit=100${status ? `&status=${status}` : ""}`, { refetchInterval: 15_000 });
  return (
    <>
      <PageHeader title="Challenges" description="Students' disputes, each with an AI recommendation for you to weigh. Marks change only when you decide."
        actions={<Select aria-label="Filter" value={status} onChange={(e) => setStatus(e.target.value)} className="w-56">
          {[["pending_teacher_review", "Awaiting your decision"], ["under_ai_review", "Under AI review"], ["", "All challenges"], ["resolved", "Resolved"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </Select>} />
      {q.isLoading ? <LoadingBlock /> : q.error ? <ErrorState error={q.error} retry={q.refetch} /> : !q.data!.items.length ? <EmptyState title="Nothing here" body="Challenges appear when students dispute a published mark." /> : (
        <Table head={["Student", "Question", "Category", "Marks", "Status", "Raised"]}>
          {q.data!.items.map((c) => (
            <tr key={c.id} className="hover:bg-canvas/50">
              <Td><Link className="font-medium hover:text-primary" href={`/teacher/challenges/${c.id}`}>{c.student}</Link></Td>
              <Td>Q{c.question_number}{c.disputed_criterion && <span className="block text-xs text-muted">{c.disputed_criterion}</span>}</Td>
              <Td>{label(c.category)}</Td>
              <Td><Marks got={c.revised_marks ?? c.original_marks} max={c.max_marks} /></Td>
              <Td><StatusBadge status={c.status} /></Td>
              <Td className="whitespace-nowrap text-muted">{fmtDate(c.created_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
