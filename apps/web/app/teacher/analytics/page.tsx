"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ClassComparison, QuestionAverages, ScoreDistribution, TopicBars } from "@/components/charts";
import { Card, EmptyState, ErrorState, LoadingBlock, PageHeader, SampleBadge, Select, Stat } from "@/components/ui";
import { useApiQuery } from "@/lib/api";
import type { Exam, Page } from "@/types/api";

type A = { examination: string; is_demo: boolean; students: number; submissions: number; evaluated_submissions: number; approved: number; class_average: number | null; median: number | null; highest: number | null; lowest: number | null;
  score_distribution: { range: string; count: number }[]; questions: { label: string; topic: string; stated_difficulty: string; average: number | null }[]; topics: { name: string; score: number }[];
  commonly_missed: { concept: string; students: number }[]; misconceptions: { issue: string; students: number }[]; reevaluation: { challenges: number; marks_changed: number; open: number } };

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <Card className="p-5"><h2 className="mb-3 font-semibold">{title}</h2>{children}</Card>;
}

function Analytics() {
  const params = useSearchParams();
  const router = useRouter();
  const exams = useApiQuery<Page<Exam>>(["exams", "analytics"], "/examinations?limit=100");
  const list = (exams.data?.items ?? []).filter((e) => !["draft", "review", "generating"].includes(e.status));
  const id = params.get("exam") || list[0]?.id || "";
  const a = useApiQuery<A>(["analytics", id], id ? `/analytics/examination/${id}` : null);
  const exam = list.find((e) => e.id === id);
  const cls = useApiQuery<{ subject: string; examinations: { examination: string; average: number }[] }>(["class", exam?.subject_id], exam ? `/analytics/class/${exam.subject_id}` : null);
  if (exams.isLoading) return <LoadingBlock />;
  if (!list.length) return <><PageHeader title="Analytics" /><EmptyState title="No published examinations yet" body="Analytics appear once a paper is published and answer sheets come in." /></>;
  const d = a.data;
  return (
    <>
      <PageHeader title="Analytics" description="Computed from recorded marks. Score distribution and topics use approved results; question averages also include provisional marks."
        actions={<Select aria-label="Examination" value={id} onChange={(e) => router.replace(`/teacher/analytics?exam=${e.target.value}`)} className="w-80">{list.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}</Select>} />
      {a.isLoading ? <LoadingBlock rows={4} /> : a.error ? <ErrorState error={a.error} retry={a.refetch} /> : d && (
        <div className="space-y-6">
          {d.is_demo && <p className="text-sm"><SampleBadge /> <span className="text-muted">This examination contains seeded demonstration records.</span></p>}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
            <Stat label="Students" value={d.students} />
            <Stat label="Submissions" value={d.submissions} />
            <Stat label="Evaluated" value={`${d.evaluated_submissions}/${d.submissions}`} />
            <Stat label="Approved" value={d.approved} />
            <Stat label="Class average" value={d.class_average !== null ? `${d.class_average}%` : "–"} />
            <Stat label="Median" value={d.median !== null ? `${d.median}%` : "–"} />
            <Stat label="Challenges" value={d.reevaluation.challenges} hint={`${d.reevaluation.marks_changed} changed marks · ${d.reevaluation.open} open`} />
          </div>
          {d.approved === 0 ? <EmptyState title="No approved results yet" body="Score distribution and topic performance appear after you approve answer sheets." /> : (
            <div className="grid gap-6 lg:grid-cols-2">
              <Panel title="Score distribution"><ScoreDistribution data={d.score_distribution} /></Panel>
              <Panel title="Average score by question"><QuestionAverages data={d.questions} /><p className="mt-2 text-xs text-muted">{d.questions.map((q) => `${q.label}: ${q.topic} (${q.stated_difficulty})`).join(" · ")}</p></Panel>
              <Panel title="Topic performance (weakest first)"><TopicBars data={d.topics} /></Panel>
              <Panel title="Commonly missed concepts">
                {d.commonly_missed.length ? <ul className="space-y-2 text-sm">{d.commonly_missed.map((m) => <li key={m.concept} className="flex justify-between"><span>{m.concept}</span><span className="tabular-nums text-muted">{m.students} answers</span></li>)}</ul> : <p className="text-sm text-muted">None recorded.</p>}
                {d.misconceptions.length > 0 && <><h3 className="mb-2 mt-5 text-sm font-semibold">Common misconceptions</h3><ul className="space-y-2 text-sm">{d.misconceptions.map((m) => <li key={m.issue} className="flex justify-between gap-3"><span>{m.issue}</span><span className="tabular-nums text-muted">{m.students}</span></li>)}</ul></>}
              </Panel>
              {cls.data && cls.data.examinations.length > 1 && <Panel title={`${cls.data.subject}: class average across examinations`}><ClassComparison data={cls.data.examinations} /></Panel>}
            </div>
          )}
        </div>
      )}
    </>
  );
}

export default function Page() {
  return <Suspense fallback={<LoadingBlock />}><Analytics /></Suspense>;
}
