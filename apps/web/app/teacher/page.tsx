"use client";

import Link from "next/link";
import { Button, Card, EmptyState, ErrorState, LoadingBlock, PageHeader, SampleBadge, Stat, StatusBadge } from "@/components/ui";
import { useMe } from "@/hooks/use-me";
import { useApiQuery } from "@/lib/api";
import { fmtDate } from "@/lib/utils";
import type { Exam, Notification, Page } from "@/types/api";

type Overview = { total_students: number; active_examinations: number; pending_submissions: number; awaiting_review: number; evaluations_completed: number; open_challenges: number };

export default function TeacherHome() {
  const me = useMe();
  const o = useApiQuery<Overview>(["teacher-overview"], "/analytics/teacher/overview", { refetchInterval: 20_000 });
  const exams = useApiQuery<Page<Exam>>(["exams", "recent"], "/examinations?limit=6");
  const activity = useApiQuery<{ items: Notification[] }>(["notifications"], "/notifications?limit=20");
  return (
    <>
      <PageHeader title={`Welcome back${me.data?.full_name ? `, ${me.data.full_name.split(" ")[0]}` : ""}`} description="What needs your attention across your examinations."
        actions={<Button asChild><Link href="/teacher/exams/new">Create examination</Link></Button>} />
      {o.error ? <ErrorState error={o.error} retry={o.refetch} /> : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
          <Stat label="Students" value={o.data?.total_students ?? "–"} />
          <Stat label="Active exams" value={o.data?.active_examinations ?? "–"} />
          <Stat label="Being processed" value={o.data?.pending_submissions ?? "–"} hint="Submitted answer sheets" />
          <Stat label="Awaiting your review" value={o.data?.awaiting_review ?? "–"} />
          <Stat label="Approved" value={o.data?.evaluations_completed ?? "–"} hint="Answer sheets signed off" />
          <Stat label="Open challenges" value={o.data?.open_challenges ?? "–"} />
        </div>
      )}
      <div className="mt-8 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <section>
          <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">Recent examinations</h2><Link href="/teacher/exams" className="text-sm text-primary hover:underline">All examinations</Link></div>
          {exams.isLoading ? <LoadingBlock /> : exams.error ? <ErrorState error={exams.error} /> : !exams.data!.items.length ? (
            <EmptyState title="No examinations yet" body="Upload course material, then generate your first paper." action={<Button asChild><Link href="/teacher/exams/new">Create examination</Link></Button>} />
          ) : (
            <Card className="divide-y divide-line">
              {exams.data!.items.map((e) => (
                <Link key={e.id} href={`/teacher/exams/${e.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-canvas/60">
                  <div className="min-w-0"><p className="truncate font-medium">{e.title}</p><p className="text-sm text-muted">{e.subject} · {e.submissions ?? 0} submissions</p></div>
                  <div className="flex shrink-0 gap-1.5">{e.is_demo && <SampleBadge />}<StatusBadge status={e.status} /></div>
                </Link>
              ))}
            </Card>
          )}
        </section>
        <section>
          <h2 className="mb-3 font-semibold">Recent activity</h2>
          <Card className="p-4">
            {activity.isLoading ? <LoadingBlock rows={4} /> : !activity.data?.items.length ? <p className="text-sm text-muted">Activity on documents, submissions and challenges appears here.</p> : (
              <ul className="space-y-3">
                {activity.data.items.slice(0, 8).map((n) => (
                  <li key={n.id} className="text-sm">
                    {n.link ? <Link href={n.link} className="font-medium hover:text-primary">{n.title}</Link> : <span className="font-medium">{n.title}</span>}
                    {n.body && <p className="text-muted">{n.body}</p>}
                    <p className="text-xs text-muted">{fmtDate(n.created_at)}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </section>
      </div>
    </>
  );
}
