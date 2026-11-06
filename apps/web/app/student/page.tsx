"use client";

import Link from "next/link";
import { Trend, TopicRadar } from "@/components/charts";
import { Button, Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Stat, StatusBadge } from "@/components/ui";
import { useMe } from "@/hooks/use-me";
import { useApiQuery } from "@/lib/api";
import { fmtDate } from "@/lib/utils";
import type { Exam, Page, Topic } from "@/types/api";

type SA = { exams_taken: number; average_percentage: number | null; trend: { examination: string; percentage: number; class_average: number; date: string }[]; subjects: { subject: string; percentage: number }[]; pending_challenges: number };

export default function StudentHome() {
  const me = useMe();
  const a = useApiQuery<SA>(["student-analytics"], "/analytics/student");
  const topics = useApiQuery<{ topics: Topic[] }>(["student-topics"], "/analytics/student/topics");
  const exams = useApiQuery<Page<Exam>>(["exams", "student"], "/examinations?limit=50");
  const upcoming = (exams.data?.items ?? []).filter((e) => e.status === "published" && !e.my_submission?.submitted_at);
  const submitted = (exams.data?.items ?? []).filter((e) => e.my_submission?.submitted_at);
  const t = topics.data?.topics ?? [];
  return (
    <>
      <PageHeader title={`Hello${me.data?.full_name ? `, ${me.data.full_name.split(" ")[0]}` : ""}`} description="Your examinations, results and where to focus next." />
      {a.error && <ErrorState error={a.error} retry={a.refetch} />}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Average" value={a.data?.average_percentage != null ? `${a.data.average_percentage}%` : "–"} hint="Across published results" />
        <Stat label="Results" value={a.data?.exams_taken ?? "–"} />
        <Stat label="To submit" value={upcoming.length} />
        <Stat label="Open challenges" value={a.data?.pending_challenges ?? "–"} />
      </div>
      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">Upcoming examinations</h2><Link href="/student/exams" className="text-sm text-primary hover:underline">All</Link></div>
          {exams.isLoading ? <LoadingBlock rows={2} /> : !upcoming.length ? <p className="text-sm text-muted">Nothing to submit right now.</p> : (
            <ul className="divide-y divide-line">{upcoming.map((e) => <li key={e.id} className="flex items-center justify-between gap-3 py-3"><div><p className="font-medium">{e.title}</p><p className="text-sm text-muted">{e.subject}{e.submission_deadline ? ` · due ${fmtDate(e.submission_deadline)}` : ""}</p></div><Button asChild size="sm"><Link href={`/student/exams/${e.id}`}>Open</Link></Button></li>)}</ul>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="mb-3 font-semibold">Submitted answer sheets</h2>
          {!submitted.length ? <p className="text-sm text-muted">Nothing submitted yet.</p> : (
            <ul className="divide-y divide-line">{submitted.map((e) => <li key={e.id} className="flex items-center justify-between gap-3 py-3"><Link href={e.status === "results_published" ? `/student/results/${e.id}` : `/student/exams/${e.id}`} className="font-medium hover:text-primary">{e.title}</Link><StatusBadge status={e.status === "results_published" ? "results_published" : e.my_submission!.status === "approved" ? "evaluated" : e.my_submission!.status} /></li>)}</ul>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="mb-1 font-semibold">Performance trend</h2>
          {!a.data?.trend.length ? <EmptyState title="No results yet" body="Your trend appears after your first result is published." /> : <Trend data={a.data.trend} />}
        </Card>
        <Card className="p-5">
          <h2 className="mb-1 font-semibold">Topic mastery</h2>
          {!t.length ? <p className="text-sm text-muted">Appears with your first published result.</p> : (<>
            <TopicRadar data={t} />
            <div className="mt-2 grid gap-4 text-sm sm:grid-cols-2">
              <div><p className="font-medium text-success">Strong</p><p className="text-muted">{t.filter((x) => x.status === "Strong").map((x) => x.name).join(", ") || "–"}</p></div>
              <div><p className="font-medium text-mark">Needs improvement</p><p className="text-muted">{t.filter((x) => x.status === "Needs Improvement").map((x) => x.name).join(", ") || "–"}</p></div>
            </div>
          </>)}
        </Card>
      </div>
    </>
  );
}
