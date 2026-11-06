"use client";

import { AlertTriangle, History } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { PageViewer } from "@/components/page-viewer";
import { Badge, Button, Card, ConfirmButton, Dialog, DialogContent, ErrorState, Field, Input, LoadingBlock, Marks, PageHeader, Select, StatusBadge, Textarea } from "@/components/ui";
import { useApiMutation, useApiQuery } from "@/lib/api";
import { fmtDate, label } from "@/lib/utils";
import type { Evaluation, ExtractedAnswer, SubmissionDetail } from "@/types/api";

function AnswerEditor({ a, onDone, inv, questions }: { a: ExtractedAnswer; onDone: () => void; inv: unknown[][]; questions: number[] }) {
  const [text, setText] = useState(a.corrected_text ?? a.recognized_text);
  const [num, setNum] = useState(a.question_number);
  const save = useApiMutation({ success: "Transcription corrected. Re-evaluate to apply it.", invalidate: inv, onSuccess: onDone });
  return (
    <div className="space-y-3">
      {a.question_number === 0 && (
        <Field label="Assign to question">{(id) => <Select id={id} value={num} onChange={(e) => setNum(Number(e.target.value))}><option value={0}>Choose…</option>{questions.map((n) => <option key={n} value={n}>Q{n}</option>)}</Select>}</Field>
      )}
      <Field label="What the student wrote" hint="Type exactly what is on the page. The original recognition is kept in the audit log.">{(id, d) => <Textarea id={id} aria-describedby={d} className="min-h-48 font-mono text-[13px]" value={text} onChange={(e) => setText(e.target.value)} />}</Field>
      <div className="flex justify-end"><Button loading={save.isPending} disabled={a.question_number === 0 && !num} onClick={() => save.mutate({ path: `/extracted-answers/${a.id}`, method: "PUT", json: { corrected_text: text, question_number: num || undefined } })}>Save correction</Button></div>
    </div>
  );
}

function ReviewForm({ ev, onDone, inv }: { ev: Evaluation; onDone: () => void; inv: unknown[][] }) {
  const [rows, setRows] = useState(ev.criteria.map((c) => ({ ...c, awarded_marks: c.awarded_marks, reason: c.reason })));
  const [reason, setReason] = useState("");
  const save = useApiMutation({ success: "Marks saved", invalidate: inv, onSuccess: onDone });
  const total = rows.reduce((s, r) => s + Number(r.awarded_marks || 0), 0);
  const bad = rows.some((r) => r.awarded_marks < 0 || r.awarded_marks > r.max_marks || r.reason.trim().length < 3);
  return (
    <div className="space-y-3">
      {ev.marks_awarded === null && <p className="text-sm text-muted">This answer could not be evaluated automatically. Mark each criterion from the original page.</p>}
      {rows.map((r, i) => (
        <fieldset key={r.criterion_id} className="rounded-[var(--radius-control)] border border-line p-3">
          <legend className="px-1 text-sm font-medium">{r.criterion} <span className="font-normal text-muted">(max {r.max_marks})</span></legend>
          <div className="grid gap-2 sm:grid-cols-[100px_1fr]">
            <Input aria-label={`${r.criterion} marks`} type="number" step="0.25" min={0} max={r.max_marks} value={r.awarded_marks} aria-invalid={r.awarded_marks > r.max_marks || r.awarded_marks < 0}
              onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, awarded_marks: Number(e.target.value) } : x)))} />
            <Input aria-label={`${r.criterion} reason`} value={r.reason} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, reason: e.target.value } : x)))} placeholder="Reason" />
          </div>
        </fieldset>
      ))}
      <Field label="Why are you changing or confirming these marks?">{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Checked the diagram on page 2" />}</Field>
      <div className="flex items-center justify-between">
        <p className="text-sm">Total <Marks got={total} max={ev.max_marks} /></p>
        <Button loading={save.isPending} disabled={reason.trim().length < 3 || bad}
          onClick={() => save.mutate({ path: `/evaluations/${ev.id}/teacher-review`, method: "PUT", json: { reason, criteria: rows.map((r) => ({ criterion_id: r.criterion_id, awarded_marks: r.awarded_marks, reason: r.reason })) } })}>Save marks</Button>
      </div>
    </div>
  );
}

function HistoryList({ id }: { id: string }) {
  const q = useApiQuery<{ items: { version: number; marks_awarded: number | null; actor_type: string; reason: string; model: string | null; created_at: string }[] }>(["history", id], `/evaluations/${id}/history`);
  if (q.isLoading) return <LoadingBlock rows={2} />;
  return <ol className="space-y-2 text-sm">{q.data?.items.map((h) => <li key={h.version} className="flex justify-between gap-3 border-b border-line pb-2"><span><span className="font-medium">v{h.version} · {h.actor_type === "ai" ? "AI evaluation" : h.actor_type === "teacher" ? "Teacher review" : "Challenge decision"}</span><br /><span className="text-muted">{h.reason}</span></span><span className="shrink-0 text-right">{h.marks_awarded ?? "–"}<br /><span className="text-xs text-muted">{fmtDate(h.created_at)}</span></span></li>)}</ol>;
}

function EvaluationPanel({ ev, answer, inv, locked, onFocus, questions }: { ev?: Evaluation; answer?: ExtractedAnswer; inv: unknown[][]; locked: boolean; onFocus: (p: number) => void; questions: number[] }) {
  const [mode, setMode] = useState<null | "answer" | "marks" | "history">(null);
  const r = ev?.report ?? {};
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{answer?.question_number === 0 ? "Unassigned text" : `Q${ev?.question_number ?? answer?.question_number}`} <span className="font-normal text-muted">{ev?.topic}</span></p>
          {ev && <p className="mt-0.5 line-clamp-2 text-sm text-muted">{ev.question_text}</p>}
        </div>
        <div className="flex items-center gap-2">{ev && <StatusBadge status={ev.status} />}{ev && <Marks got={ev.marks_awarded} max={ev.max_marks} className="text-lg" />}</div>
      </div>
      {!!ev?.review_reasons?.length && (
        <div className="mt-3 rounded-[var(--radius-control)] bg-mark-soft p-3 text-sm text-mark"><p className="flex items-center gap-1.5 font-medium"><AlertTriangle className="h-4 w-4" aria-hidden />Needs your review</p><ul className="mt-1 list-inside list-disc">{ev.review_reasons.map((x) => <li key={x}>{x}</li>)}</ul></div>
      )}
      {answer && (
        <div className="mt-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span>Recognition {Math.round(answer.ocr_confidence * 100)}%</span>
            {answer.corrected_text !== null && <Badge tone="primary">Corrected by teacher</Badge>}
            {answer.contains_diagram && <Badge>Diagram</Badge>}{answer.contains_equation && <Badge>Equation</Badge>}
            {answer.pages.map((p) => <button key={p} className="text-primary underline" onClick={() => onFocus(p)}>page {p}</button>)}
          </div>
          <p className="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap rounded-[var(--radius-control)] bg-canvas p-3 font-mono text-[13px] leading-relaxed">{(answer.corrected_text ?? answer.recognized_text) || "(empty)"}</p>
        </div>
      )}
      {ev && ev.criteria.length > 0 && (
        <ul className="mt-4 divide-y divide-line text-sm">
          {ev.criteria.map((c) => <li key={c.criterion_id} className="flex justify-between gap-4 py-2"><span><span className="font-medium">{c.criterion}</span><br /><span className="text-muted">{c.reason}</span></span><Marks got={c.awarded_marks} max={c.max_marks} className="shrink-0" /></li>)}
        </ul>
      )}
      {ev && (
        <div className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
          {[["Covered", r.covered_points, "success"], ["Partial", r.partially_covered_points, "warning"], ["Missing", r.missing_points, "mark"]].map(([k, v, t]) => (
            <div key={k as string}><p className="text-xs text-muted">{k as string}</p><div className="mt-1 flex flex-wrap gap-1">{(v as string[] | undefined)?.length ? (v as string[]).map((x) => <Badge key={x} tone={t as "success"}>{x}</Badge>) : <span className="text-muted">–</span>}</div></div>
          ))}
        </div>
      )}
      {!!r.valid_alternative_points?.length && <p className="mt-3 text-sm"><span className="text-muted">Valid alternatives credited:</span> {r.valid_alternative_points.join("; ")}</p>}
      {!!r.incorrect_statements?.length && <div className="mt-3 text-sm"><p className="text-xs text-muted">Incorrect statements</p><ul className="mt-1 space-y-1">{r.incorrect_statements.map((s, i) => <li key={i}><q className="text-mark">{s.quote}</q> — {s.explanation}</li>)}</ul></div>}
      {ev?.confidence !== undefined && <p className="mt-3 text-xs text-muted">Confidence signal {Math.round(ev.confidence * 100)}% (an indicator for review, not proof of correctness){ev.model ? ` · ${ev.model}` : ""} · version {ev.version}</p>}
      <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
        {answer && !locked && <Button size="sm" variant="secondary" onClick={() => setMode("answer")}>{answer.question_number === 0 ? "Assign and correct" : "Correct transcription"}</Button>}
        {ev && !locked && <Button size="sm" variant={ev.requires_human_review ? "primary" : "secondary"} onClick={() => setMode("marks")}>{ev.requires_human_review ? "Review marks" : "Adjust marks"}</Button>}
        {ev && <Button size="sm" variant="ghost" onClick={() => setMode("history")}><History className="h-3.5 w-3.5" />History</Button>}
      </div>
      <Dialog open={!!mode} onOpenChange={(o) => !o && setMode(null)}>
        {mode === "answer" && answer && <DialogContent wide title="Correct the transcription"><AnswerEditor a={answer} inv={inv} questions={questions} onDone={() => setMode(null)} /></DialogContent>}
        {mode === "marks" && ev && <DialogContent wide title={`Marks for Q${ev.question_number}`} description="Marks are entered per rubric criterion. Each change is versioned."><ReviewForm ev={ev} inv={inv} onDone={() => setMode(null)} /></DialogContent>}
        {mode === "history" && ev && <DialogContent title={`Q${ev.question_number} history`}><HistoryList id={ev.id} /></DialogContent>}
      </Dialog>
    </Card>
  );
}

export default function SubmissionReview() {
  const { id } = useParams<{ id: string }>();
  const q = useApiQuery<SubmissionDetail>(["submission", id], `/submissions/${id}`, { refetchInterval: (x) => (["submitted", "extracting", "extracted", "evaluating"].includes(x.state.data?.status ?? "") ? 3000 : false) });
  const inv = [["submission", id]];
  const approve = useApiMutation({ success: "Approved. Publish results from the examination page when ready.", invalidate: inv });
  const reeval = useApiMutation({ success: "Re-evaluation started", invalidate: inv });
  const reprocess = useApiMutation({ success: "Reprocessing the answer sheet", invalidate: inv });
  const [focus, setFocus] = useState<number>();
  if (q.isLoading) return <LoadingBlock rows={6} />;
  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />;
  const s = q.data!;
  const evals = new Map(s.evaluations.map((e) => [e.question_number, e]));
  const answers = new Map(s.answers.map((a) => [a.question_number, a]));
  const numbers = Array.from(new Set([...evals.keys(), ...answers.keys()])).sort((a, b) => (a || 99) - (b || 99));
  const flagged = s.evaluations.filter((e) => e.requires_human_review || e.marks_awarded === null).length;
  const total = s.evaluations.reduce((t, e) => t + (e.marks_awarded ?? 0), 0);
  const max = s.evaluations.reduce((t, e) => t + e.max_marks, 0);
  const locked = s.status === "approved";
  const busy = ["submitted", "extracting", "extracted", "evaluating"].includes(s.status);
  return (
    <>
      <PageHeader back={<Link href={`/teacher/exams/${s.examination_id}`} className="text-muted hover:text-ink">{s.examination}</Link>}
        title={<span className="flex flex-wrap items-center gap-2">{s.student}<StatusBadge status={s.status} /></span>}
        description={<>Submitted {fmtDate(s.submitted_at)} · {s.page_count} pages · version {s.version}{s.result && <> · result {label(s.result.status)}</>}</>}
        actions={<>
          {s.status === "failed" && <Button loading={reprocess.isPending} onClick={() => reprocess.mutate({ path: `/submissions/${id}/process` })}>Reprocess answer sheet</Button>}
          {["evaluated", "failed"].includes(s.status) && s.answers.length > 0 && <ConfirmButton title="Re-evaluate this answer sheet?" body="Answers that are not yet approved are marked again using your corrected transcriptions. Previous versions stay in the history." confirmLabel="Re-evaluate" danger={false} variant="secondary" size="md" onConfirm={() => reeval.mutateAsync({ path: `/submissions/${id}/reevaluate` })}>Re-evaluate</ConfirmButton>}
          {s.status === "evaluated" && <ConfirmButton title="Approve these marks?" body={`The total of ${total} / ${max} becomes final for this student. It is shown to them once you publish results.`} confirmLabel="Approve marks" danger={false} variant="primary" size="md" disabled={flagged > 0}
            onConfirm={() => approve.mutateAsync({ path: `/evaluations/submission/${id}/approve` })}>{flagged ? `${flagged} answer${flagged > 1 ? "s" : ""} to review` : "Approve marks"}</ConfirmButton>}
        </>} />
      {busy && <Card className="mb-4 p-4 text-sm">{s.status === "extracting" && s.extraction ? `Reading handwriting: page ${s.extraction.pages_done} of ${s.extraction.pages_total}…` : s.status === "evaluating" ? `Evaluating answers against the rubric: ${s.evaluations.length} done…` : "Queued for processing…"}</Card>}
      {!!s.extraction?.page_failures.length && <div className="mb-4"><ErrorState error={{ message: `Pages that could not be read: ${s.extraction.page_failures.map((f) => `page ${f.page} (${f.error})`).join("; ")}. Reprocess, or correct the affected answers by hand.` }} /></div>}
      {!!s.extraction?.warnings.length && <Card className="mb-4 border-warning/30 bg-warning-soft p-4 text-sm"><p className="font-medium text-warning">Check the scan</p><ul className="mt-1 list-inside list-disc">{s.extraction.warnings.map((w) => <li key={w}>{w}</li>)}</ul></Card>}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="xl:sticky xl:top-20 xl:self-start"><PageViewer submissionId={id} focus={focus} /></div>
        <div className="space-y-4">
          {max > 0 && <Card className="flex items-center justify-between p-4"><span className="text-sm text-muted">{locked ? "Approved total" : "Provisional total"}</span><Marks got={total} max={max} className="text-xl" /></Card>}
          {numbers.map((n) => <EvaluationPanel key={n} ev={evals.get(n)} answer={answers.get(n)} inv={inv} locked={locked} onFocus={setFocus} questions={Array.from(evals.keys())} />)}
          {!numbers.length && !busy && <p className="text-sm text-muted">No answers recognised yet.</p>}
        </div>
      </div>
    </>
  );
}
