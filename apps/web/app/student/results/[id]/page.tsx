"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { TopicBars } from "@/components/charts";
import { PageViewer } from "@/components/page-viewer";
import { Badge, Button, Card, Dialog, DialogContent, ErrorState, Field, LoadingBlock, Marks, PageHeader, SampleBadge, Select, StatusBadge, Textarea } from "@/components/ui";
import { useApiMutation, useApiQuery } from "@/lib/api";
import { cn, label } from "@/lib/utils";
import type { Evaluation, Topic } from "@/types/api";

type Result = { examination: string; subject: string; submission_id: string; total_marks: number; max_marks: number; percentage: number; is_demo: boolean; published_at: string; questions: Evaluation[]; topics: Topic[];
  insights: { strengths?: string[]; weaknesses?: string[]; recommendations?: { topic: string; type: string; text: string; evidence_questions: number[] }[] } };

const CATEGORIES = [["incorrect_deduction", "Marks were deducted incorrectly"], ["missed_concept", "A valid point I made was missed"], ["incomplete_answer_key", "The answer key is incomplete"], ["incorrect_rubric", "The rubric is wrong"], ["ambiguous_question", "The question was ambiguous"], ["handwriting_error", "My handwriting was misread"], ["diagram_interpretation", "My diagram was misinterpreted"]];

function ChallengeForm({ ev, examId, onDone }: { ev: Evaluation; examId: string; onDone: () => void }) {
  const [category, setCategory] = useState("incorrect_deduction");
  const [criterion, setCriterion] = useState("");
  const [text, setText] = useState("");
  const [evidence, setEvidence] = useState("");
  const submit = useApiMutation({ success: "Challenge submitted. Your teacher will review it.", invalidate: [["result", examId], ["challenges"]], onSuccess: onDone });
  const short = text.trim().length < 20;
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (!short) submit.mutate({ path: "/challenges", json: { evaluation_id: ev.id, category, rubric_criterion_id: criterion || null, explanation: text, evidence: evidence.trim() ? [evidence.trim()] : [] } }); }}>
      <div className="rounded-[var(--radius-control)] bg-canvas p-3 text-sm"><p className="font-medium">Q{ev.question_number}: <Marks got={ev.marks_awarded} max={ev.max_marks} /></p><p className="mt-1 text-muted">{ev.question_text}</p></div>
      <Field label="What are you challenging?">{(id) => <Select id={id} value={category} onChange={(e) => setCategory(e.target.value)}>{CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>}</Field>
      <Field label="Which criterion?">{(id) => <Select id={id} value={criterion} onChange={(e) => setCriterion(e.target.value)}><option value="">The whole question</option>{ev.criteria.map((c) => <option key={c.criterion_id} value={c.criterion_id}>{c.criterion} ({c.awarded_marks}/{c.max_marks})</option>)}</Select>}</Field>
      <Field label="Explain why" error={text && short ? "Write at least 20 characters" : undefined} hint="Point to where in your answer you made the point, and why it is correct.">{(id, d) => <Textarea id={id} aria-describedby={d} className="min-h-32" value={text} onChange={(e) => setText(e.target.value)} />}</Field>
      <Field label="Supporting reference (optional)" hint="e.g. a textbook page or a quote from the lecture notes">{(id, d) => <Textarea id={id} aria-describedby={d} className="min-h-16" value={evidence} onChange={(e) => setEvidence(e.target.value)} />}</Field>
      <div className="flex justify-end"><Button type="submit" loading={submit.isPending} disabled={short}>Submit challenge</Button></div>
    </form>
  );
}

function QuestionResult({ ev, examId, sample }: { ev: Evaluation; examId: string; sample: boolean }) {
  const [open, setOpen] = useState(false);
  const [challenge, setChallenge] = useState(false);
  const [page, setPage] = useState(false);
  const r = ev.report;
  return (
    <Card className="p-5">
      <button className="flex w-full items-start justify-between gap-4 text-left" aria-expanded={open} onClick={() => setOpen(!open)}>
        <div className="min-w-0"><p className="font-semibold">Q{ev.question_number} <span className="font-normal text-muted">· {ev.topic}</span></p><p className="mt-0.5 text-sm text-muted">{ev.question_text}</p></div>
        <div className="flex shrink-0 items-center gap-2"><Marks got={ev.marks_awarded} max={ev.max_marks} className="text-lg" /><ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} aria-hidden /></div>
      </button>
      {open && (
        <div className="mt-4 space-y-4 border-t border-line pt-4 text-sm">
          {r.seeded && <p><SampleBadge /> <span className="text-muted">Seeded demonstration record.</span></p>}
          {ev.answer_text && <div><p className="text-xs text-muted">Your answer as read from your sheet</p><p className="mt-1 whitespace-pre-wrap rounded-[var(--radius-control)] bg-canvas p-3">{ev.answer_text}</p>
            {ev.pages.length > 0 && <Button size="sm" variant="link" onClick={() => setPage(true)}>View your original page{ev.pages.length > 1 ? "s" : ""} ({ev.pages.join(", ")})</Button>}</div>}
          <div><p className="text-xs text-muted">Marks by criterion</p>
            <ul className="mt-1 divide-y divide-line">{ev.criteria.map((c) => <li key={c.criterion_id} className="flex justify-between gap-3 py-2"><span><span className="font-medium">{c.criterion}</span><br /><span className="text-muted">{c.reason}</span></span><Marks got={c.awarded_marks} max={c.max_marks} /></li>)}</ul>
          </div>
          <div><p className="text-xs text-muted">Expected concepts</p><div className="mt-1 flex flex-wrap gap-1.5">{ev.expected_concepts.map((c) => {
            const t = r.covered_points?.includes(c) ? "success" : r.partially_covered_points?.includes(c) ? "warning" : r.missing_points?.includes(c) ? "mark" : "neutral";
            return <Badge key={c} tone={t as "success"}>{c}{t === "success" ? " · covered" : t === "warning" ? " · partly" : t === "mark" ? " · missing" : ""}</Badge>;
          })}</div></div>
          {!!r.incorrect_statements?.length && <div><p className="text-xs text-muted">Statements that were incorrect</p><ul className="mt-1 space-y-1">{r.incorrect_statements.map((s, i) => <li key={i}><q className="text-mark">{s.quote}</q> — {s.explanation}</li>)}</ul></div>}
          {(r.strengths?.length || r.improvements?.length) ? <div className="grid gap-4 sm:grid-cols-2">
            <div><p className="text-xs text-muted">What went well</p><ul className="mt-1 list-inside list-disc">{r.strengths?.map((s) => <li key={s}>{s}</li>)}</ul></div>
            <div><p className="text-xs text-muted">How to improve</p><ul className="mt-1 list-inside list-disc">{r.improvements?.map((s) => <li key={s}>{s}</li>)}</ul></div>
          </div> : null}
          {r.overall_feedback && !r.seeded && <p>{r.overall_feedback}</p>}
          {r.suggested_improved_answer && <div><p className="text-xs text-muted">A stronger answer could read</p><p className="mt-1 whitespace-pre-wrap rounded-[var(--radius-control)] border border-line p-3">{r.suggested_improved_answer}</p></div>}
          <div className="flex items-center gap-3 border-t border-line pt-3">
            {ev.challenge ? <><span className="text-muted">Challenge</span><StatusBadge status={ev.challenge.status} /><Link className="text-primary hover:underline" href={`/student/challenges/${ev.challenge.id}`}>View</Link></> : !sample && <Button size="sm" variant="secondary" onClick={() => setChallenge(true)}>Challenge this mark</Button>}
          </div>
        </div>
      )}
      <Dialog open={challenge} onOpenChange={setChallenge}><DialogContent title="Challenge a mark" description="Your teacher sees your reasoning together with an AI review of it, and makes the decision."><ChallengeForm ev={ev} examId={examId} onDone={() => setChallenge(false)} /></DialogContent></Dialog>
      <Dialog open={page} onOpenChange={setPage}><DialogContent wide title={`Your answer to Q${ev.question_number}`}><PageViewer submissionId={ev.submission_id} focus={ev.pages[0]} /></DialogContent></Dialog>
    </Card>
  );
}

export default function ResultPage() {
  const { id } = useParams<{ id: string }>();
  const q = useApiQuery<Result>(["result", id], `/results/${id}`);
  if (q.isLoading) return <LoadingBlock rows={6} />;
  if (q.error) return <ErrorState error={q.error.status === 404 ? { message: "This result has not been published yet." } : q.error} />;
  const r = q.data!;
  return (
    <>
      <PageHeader back={<Link href="/student/results" className="text-muted hover:text-ink">Results</Link>} title={<span className="flex flex-wrap items-center gap-2">{r.examination}{r.is_demo && <SampleBadge />}</span>} description={r.subject} />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
        <div className="space-y-4">
          <Card className="p-6">
            <p className="text-sm text-muted">Total</p>
            <p className="mt-1 text-4xl"><Marks got={r.total_marks} max={r.max_marks} /></p>
            <p className="mt-1 text-lg tabular-nums">{r.percentage}%</p>
          </Card>
          <Card className="p-5"><h2 className="mb-2 font-semibold">By topic</h2><TopicBars data={r.topics} />
            <ul className="mt-3 space-y-1 text-sm">{r.topics.map((t) => <li key={t.name} className="flex justify-between"><span>{t.name}</span><StatusBadge status={t.status} /></li>)}</ul>
          </Card>
          {!!r.insights.recommendations?.length && (
            <Card className="p-5"><h2 className="font-semibold">What to work on</h2>
              <ul className="mt-3 space-y-3 text-sm">{r.insights.recommendations.map((x, i) => (
                <li key={i}><Badge tone={x.type === "conceptual" ? "mark" : x.type === "explanation" ? "warning" : "primary"}>{x.type === "conceptual" ? "Understanding" : x.type === "explanation" ? "Explaining" : "Skill"}</Badge><p className="mt-1">{x.text}</p><p className="text-xs text-muted">Based on {x.evidence_questions.map((n) => `Q${n}`).join(", ")}</p></li>
              ))}</ul>
            </Card>
          )}
        </div>
        <div className="space-y-3">
          <h2 className="font-semibold">Question by question</h2>
          {r.questions.map((ev) => <QuestionResult key={ev.id} ev={ev} examId={id} sample={r.is_demo} />)}
        </div>
      </div>
    </>
  );
}
