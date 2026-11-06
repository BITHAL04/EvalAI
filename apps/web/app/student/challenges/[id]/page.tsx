"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Card, ErrorState, LoadingBlock, Marks, PageHeader, StatusBadge } from "@/components/ui";
import { useApiQuery } from "@/lib/api";
import { fmtDate, label } from "@/lib/utils";
import type { Challenge } from "@/types/api";

const STEPS = ["submitted", "under_ai_review", "pending_teacher_review", "decided", "resolved"];
const NAMES: Record<string, string> = { submitted: "Submitted", under_ai_review: "AI review", pending_teacher_review: "Teacher review", decided: "Decision", resolved: "Resolved" };

export default function MyChallenge() {
  const { id } = useParams<{ id: string }>();
  const q = useApiQuery<Challenge>(["challenge", id], `/challenges/${id}`, { refetchInterval: 15_000 });
  if (q.isLoading) return <LoadingBlock />;
  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />;
  const c = q.data!;
  const at = ["accepted", "partially_accepted", "rejected"].includes(c.status) ? 3 : STEPS.indexOf(c.status);
  return (
    <>
      <PageHeader back={<Link href="/student/challenges" className="text-muted hover:text-ink">Challenges</Link>} title={<span className="flex items-center gap-2">Challenge on Q{c.question_number}<StatusBadge status={c.status} /></span>} description={`${label(c.category)} · raised ${fmtDate(c.created_at)}`} />
      <ol className="mb-6 grid grid-cols-5 gap-2 text-xs" aria-label="Progress">
        {STEPS.map((s, i) => <li key={s} aria-current={i === at ? "step" : undefined} className={`border-t-2 pt-2 ${i <= at ? "border-primary text-ink" : "border-line text-muted"}`}>{NAMES[s]}</li>)}
      </ol>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5 text-sm">
          <p className="text-muted">Question</p><p className="mt-1">{c.question_text}</p>
          {c.disputed_criterion && <><p className="mt-4 text-muted">Criterion</p><p className="mt-1">{c.disputed_criterion}</p></>}
          <p className="mt-4 text-muted">Your explanation</p><p className="mt-1 whitespace-pre-wrap">{c.explanation}</p>
        </Card>
        <Card className="p-5 text-sm">
          <div className="flex justify-between"><span className="text-muted">Original marks</span><Marks got={c.original_marks} max={c.max_marks} /></div>
          {c.decisions.length ? c.decisions.map((d, i) => (
            <div key={i} className="mt-4 border-t border-line pt-4">
              <div className="flex justify-between"><span className="font-semibold">{label(d.decision)}</span><Marks got={d.revised_marks} max={c.max_marks} /></div>
              <p className="mt-2">{d.reason}</p><p className="mt-1 text-xs text-muted">{fmtDate(d.decided_at)}</p>
            </div>
          )) : <p className="mt-4 text-muted">Your teacher has not decided yet. You will be notified when they do.</p>}
        </Card>
      </div>
    </>
  );
}
