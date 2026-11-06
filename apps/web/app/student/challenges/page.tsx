"use client";

import Link from "next/link";
import { EmptyState, ErrorState, LoadingBlock, Marks, PageHeader, StatusBadge, Table, Td } from "@/components/ui";
import { useApiQuery } from "@/lib/api";
import { fmtDate, label } from "@/lib/utils";
import type { Challenge, Page } from "@/types/api";

export default function MyChallenges() {
  const q = useApiQuery<Page<Challenge>>(["challenges"], "/challenges?limit=100");
  return (
    <>
      <PageHeader title="Challenges" description="Disputes you have raised and their outcome. Start a challenge from a published result." />
      {q.isLoading ? <LoadingBlock /> : q.error ? <ErrorState error={q.error} retry={q.refetch} /> : !q.data!.items.length ? <EmptyState title="No challenges" body="If you think a mark is wrong, open the result and choose Challenge this mark." /> : (
        <Table head={["Question", "Category", "Original", "Revised", "Status", "Raised"]}>
          {q.data!.items.map((c) => (
            <tr key={c.id}>
              <Td><Link className="font-medium hover:text-primary" href={`/student/challenges/${c.id}`}>Q{c.question_number}</Link><p className="line-clamp-1 text-xs text-muted">{c.question_text}</p></Td>
              <Td>{label(c.category)}</Td><Td><Marks got={c.original_marks} max={c.max_marks} /></Td><Td>{c.revised_marks !== null ? <Marks got={c.revised_marks} max={c.max_marks} /> : "–"}</Td>
              <Td><StatusBadge status={c.status} /></Td><Td className="whitespace-nowrap text-muted">{fmtDate(c.created_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
