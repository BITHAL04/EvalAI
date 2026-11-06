"use client";

import Link from "next/link";
import { Button, Card, EmptyState, ErrorState, LoadingBlock, PageHeader, SampleBadge, StatusBadge } from "@/components/ui";
import { useApiQuery } from "@/lib/api";
import { fmtDate } from "@/lib/utils";
import type { Exam, Page } from "@/types/api";

export default function StudentExams() {
  const q = useApiQuery<Page<Exam>>(["exams", "student"], "/examinations?limit=100");
  return (
    <>
      <PageHeader title="Examinations" description="Papers published for subjects you are enrolled in." />
      {q.isLoading ? <LoadingBlock /> : q.error ? <ErrorState error={q.error} retry={q.refetch} /> : !q.data!.items.length ? <EmptyState title="No examinations yet" body="When your teacher publishes a paper it appears here." /> : (
        <div className="grid gap-4 md:grid-cols-2">
          {q.data!.items.map((e) => (
            <Card key={e.id} className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-3"><div><p className="text-sm text-muted">{e.subject}</p><h2 className="font-semibold">{e.title}</h2></div><div className="flex gap-1">{e.is_demo && <SampleBadge />}<StatusBadge status={e.my_submission?.submitted_at ? e.my_submission.status : e.status} /></div></div>
              <p className="mt-2 text-sm text-muted">{e.total_marks} marks · {e.duration_minutes} minutes{e.submission_deadline ? ` · due ${fmtDate(e.submission_deadline)}` : ""}</p>
              <div className="mt-4 flex gap-2">
                {e.status === "results_published" && e.my_submission ? <Button asChild size="sm"><Link href={`/student/results/${e.id}`}>View result</Link></Button> : <Button asChild size="sm"><Link href={`/student/exams/${e.id}`}>{e.my_submission?.submitted_at ? "View submission" : "Open"}</Link></Button>}
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
