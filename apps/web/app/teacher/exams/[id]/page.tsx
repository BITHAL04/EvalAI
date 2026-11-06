"use client";

import { ChevronDown, Download, Loader2, Plus, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { QuestionEditor, emptyQuestion, type QuestionDraft } from "@/components/teacher/question-editor";
import { Badge, Button, Card, ConfirmButton, Dialog, DialogContent, EmptyState, ErrorState, Field, LoadingBlock, Marks, PageHeader, SampleBadge, Select, StatusBadge, Table, Tabs, TabsContent, TabsList, TabsTrigger, Td, Textarea, Input } from "@/components/ui";
import { useApi, useApiMutation, useApiQuery } from "@/lib/api";
import { fmtDate, label } from "@/lib/utils";
import type { ExamDetail, ExamQuestion } from "@/types/api";

type SubRow = { id: string; student: string; roll_number: string | null; status: string; version: number; submitted_at: string | null; provisional_marks: number | null; flagged: number; evaluated: number; result_status: string | null };

function QuestionCard({ q, editable, examId }: { q: ExamQuestion; editable: boolean; examId: string }) {
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState(false);
  const inv = [["exam", examId]];
  const save = useApiMutation({ success: "Question saved", invalidate: inv, onSuccess: () => setEdit(false) });
  const regen = useApiMutation({ success: "Regenerating this question", invalidate: inv });
  const del = useApiMutation({ success: "Question deleted", invalidate: inv });
  const draft: QuestionDraft = { ...q, rubric: q.rubric?.criteria.map(({ criterion, category, max_marks, expected_evidence }) => ({ criterion, category, max_marks, expected_evidence })) ?? [] };
  return (
    <Card className="p-5">
      <div className="flex gap-4">
        <span className="text-lg font-semibold tabular-nums text-primary">Q{q.question_number}</span>
        <div className="min-w-0 flex-1">
          <p className="leading-relaxed">{q.question_text}</p>
          <div className="mt-2 flex flex-wrap gap-1.5"><Badge tone="primary">{q.marks} marks</Badge><Badge>{q.topic}</Badge><Badge>{q.difficulty}</Badge><Badge>{label(q.question_type)}</Badge>{q.origin === "ai" && <Badge>AI generated</Badge>}{q.rubric && <Badge tone={q.rubric.status === "approved" ? "success" : "neutral"}>Rubric v{q.rubric.version} · {q.rubric.status}</Badge>}</div>
          <button className="mt-3 inline-flex items-center gap-1 text-sm text-primary" aria-expanded={open} onClick={() => setOpen(!open)}><ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />Answer key, rubric and sources</button>
          {open && (
            <div className="mt-3 space-y-4 border-t border-line pt-4 text-sm">
              <div><p className="font-medium">Model answer</p><p className="mt-1 whitespace-pre-wrap text-muted">{q.expected_answer}</p></div>
              <div><p className="font-medium">Expected concepts</p><div className="mt-1 flex flex-wrap gap-1.5">{q.expected_concepts.map((c) => <Badge key={c}>{c}</Badge>)}</div></div>
              {q.rubric && (
                <div><p className="font-medium">Rubric</p>
                  <ul className="mt-1 divide-y divide-line rounded-[var(--radius-control)] border border-line">
                    {q.rubric.criteria.map((c) => <li key={c.id} className="flex gap-3 px-3 py-2"><span className="w-10 shrink-0 font-semibold tabular-nums">{c.max_marks}</span><span><span className="font-medium">{c.criterion}</span> <span className="text-muted">({label(c.category)})</span><br /><span className="text-muted">{c.expected_evidence}</span></span></li>)}
                  </ul>
                </div>
              )}
              <div><p className="font-medium">Generated from</p>
                {q.source_references.length ? <ul className="mt-1 list-inside list-disc text-muted">{q.source_references.map((r) => <li key={r.chunk_id}>{r.material_title}, pages {r.page_start}{r.page_end && r.page_end !== r.page_start ? `–${r.page_end}` : ""}{r.chapter ? ` (${r.chapter})` : ""}</li>)}</ul> : <p className="mt-1 text-muted">No source recorded (written by hand or from the bank).</p>}
              </div>
            </div>
          )}
        </div>
        {editable && (
          <div className="flex shrink-0 flex-col gap-1 sm:flex-row sm:items-start">
            <Button size="sm" variant="secondary" onClick={() => setEdit(true)}>Edit</Button>
            <ConfirmButton title={`Regenerate Q${q.question_number}?`} body="A new question with the same marks, difficulty and topic replaces this one, along with its answer key and rubric." confirmLabel="Regenerate" danger={false} variant="ghost"
              onConfirm={() => regen.mutateAsync({ path: `/examination-questions/${q.id}/regenerate` })}><RefreshCw className="h-3.5 w-3.5" /><span className="sr-only">Regenerate</span></ConfirmButton>
            <ConfirmButton title={`Delete Q${q.question_number}?`} body="Remaining questions are renumbered. Recalculate the total marks afterwards." confirmLabel="Delete question" variant="ghost"
              onConfirm={() => del.mutateAsync({ path: `/examination-questions/${q.id}`, method: "DELETE" })}><Trash2 className="h-3.5 w-3.5" /><span className="sr-only">Delete</span></ConfirmButton>
          </div>
        )}
      </div>
      <Dialog open={edit} onOpenChange={setEdit}>
        <DialogContent wide title={`Edit Q${q.question_number}`}>
          <QuestionEditor initial={draft} lockType saving={save.isPending} submitLabel="Save question" onSave={(v) => save.mutate({ path: `/examination-questions/${q.id}`, method: "PUT", json: { question_text: v.question_text, topic: v.topic, difficulty: v.difficulty, marks: v.marks, expected_answer: v.expected_answer, expected_concepts: v.expected_concepts, rubric: v.rubric } })} />
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Submissions({ examId, max }: { examId: string; max: number }) {
  const q = useApiQuery<{ items: SubRow[] }>(["exam-subs", examId], `/examinations/${examId}/submissions`, { refetchInterval: (x) => (x.state.data?.items.some((s) => ["submitted", "extracting", "extracted", "evaluating"].includes(s.status)) ? 4000 : false) });
  if (q.isLoading) return <LoadingBlock />;
  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />;
  if (!q.data!.items.length) return <EmptyState title="No submissions yet" body="Students' uploaded answer sheets appear here as they are processed." />;
  return (
    <Table head={["Student", "Submitted", "Status", "Provisional marks", "Flagged", "Result", ""]}>
      {q.data!.items.map((s) => (
        <tr key={s.id}>
          <Td><p className="font-medium">{s.student}</p>{s.roll_number && <p className="text-xs text-muted">{s.roll_number}</p>}</Td>
          <Td className="whitespace-nowrap text-muted">{fmtDate(s.submitted_at)}{s.version > 1 && <span className="block text-xs">Version {s.version}</span>}</Td>
          <Td><StatusBadge status={s.status} /></Td>
          <Td><Marks got={s.provisional_marks} max={max} /></Td>
          <Td>{s.flagged ? <Badge tone="mark">{s.flagged} to review</Badge> : <span className="text-muted">–</span>}</Td>
          <Td>{s.result_status ? <StatusBadge status={s.result_status} /> : <span className="text-muted">–</span>}</Td>
          <Td className="text-right"><Button asChild size="sm" variant="secondary"><Link href={`/teacher/submissions/${s.id}`}>Review</Link></Button></Td>
        </tr>
      ))}
    </Table>
  );
}

function Calibration({ exam }: { exam: ExamDetail }) {
  const [qid, setQid] = useState(exam.questions[0]?.id ?? "");
  const [tier, setTier] = useState("strong");
  const [text, setText] = useState("");
  const [marks, setMarks] = useState("");
  const bm = useApiQuery<{ items: { id: string; tier: string; answer_text: string; expected_marks: number; last_ai_marks: number | null }[] }>(["benchmarks", qid], qid ? `/examination-questions/${qid}/benchmarks` : null);
  const add = useApiMutation({ success: "Reference answer saved", invalidate: [["benchmarks", qid]], onSuccess: () => { setText(""); setMarks(""); } });
  const run = useApiMutation({ success: "Calibration started. Results appear below when finished.", invalidate: [["exam", exam.id]] });
  const q = exam.questions.find((x) => x.id === qid);
  const published = !["draft", "review", "generating"].includes(exam.status);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="p-5">
        <h3 className="font-semibold">Reference answers</h3>
        <p className="mt-1 text-sm text-muted">Write a strong, an average and a weak answer with the marks you would give. Calibration grades them with the same pipeline and reports any drift.</p>
        <div className="mt-4 space-y-3">
          <Select aria-label="Question" value={qid} onChange={(e) => setQid(e.target.value)}>{exam.questions.map((x) => <option key={x.id} value={x.id}>Q{x.question_number} · {x.question_text.slice(0, 70)}</option>)}</Select>
          {bm.data?.items.map((b) => <div key={b.id} className="rounded-[var(--radius-control)] border border-line p-3 text-sm"><div className="flex justify-between"><span className="font-medium capitalize">{b.tier}</span><span>Yours {b.expected_marks} · AI {b.last_ai_marks ?? "not run"}</span></div><p className="mt-1 line-clamp-2 text-muted">{b.answer_text}</p></div>)}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Tier">{(id) => <Select id={id} value={tier} onChange={(e) => setTier(e.target.value)}><option value="strong">Strong</option><option value="average">Average</option><option value="weak">Weak</option></Select>}</Field>
            <Field label={`Your marks (of ${q?.marks ?? "–"})`}>{(id) => <Input id={id} type="number" step="0.25" min={0} max={q?.marks} value={marks} onChange={(e) => setMarks(e.target.value)} />}</Field>
          </div>
          <Field label="Answer text">{(id) => <Textarea id={id} value={text} onChange={(e) => setText(e.target.value)} />}</Field>
          <Button disabled={text.trim().length < 10 || marks === "" || Number(marks) > (q?.marks ?? 0)} loading={add.isPending} onClick={() => add.mutate({ path: `/examination-questions/${qid}/benchmarks`, json: { tier, answer_text: text, expected_marks: Number(marks) } })}>Save reference answer</Button>
        </div>
      </Card>
      <Card className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div><h3 className="font-semibold">Consistency report</h3><p className="mt-1 text-sm text-muted">Outliers, near-identical answers with different marks, and drift from your reference answers.</p></div>
          <Button size="sm" variant="secondary" disabled={!published} title={published ? undefined : "Publish the paper first"} loading={run.isPending} onClick={() => run.mutate({ path: `/examinations/${exam.id}/calibrate` })}>Run calibration</Button>
        </div>
        {!exam.consistency ? <p className="mt-6 text-sm text-muted">No report yet. One is produced after answer sheets are evaluated or calibration runs.</p> : (
          <div className="mt-4">
            <p className="text-xs text-muted">Updated {fmtDate(exam.consistency.created_at)} · {String(exam.consistency.summary.answers ?? 0)} answers checked</p>
            {!exam.consistency.findings.length ? <p className="mt-3 text-sm text-success">No inconsistencies found.</p> : (
              <ul className="mt-3 space-y-2">{exam.consistency.findings.map((f, i) => <li key={i} className="rounded-[var(--radius-control)] bg-warning-soft p-3 text-sm"><span className="font-medium">{f.question_number ? `Q${f.question_number}: ` : ""}{label(f.type)}</span><br />{f.detail}</li>)}</ul>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

export default function ExamPage() {
  const { id } = useParams<{ id: string }>();
  const api = useApi();
  const q = useApiQuery<ExamDetail>(["exam", id], `/examinations/${id}`, { refetchInterval: (x) => (x.state.data?.status === "generating" ? 3000 : false) });
  const inv = [["exam", id], ["exams"]];
  const publish = useApiMutation({ success: "Published. Enrolled students have been notified.", invalidate: inv });
  const recalc = useApiMutation({ success: "Total marks updated", invalidate: inv });
  const close = useApiMutation({ success: "Submissions closed", invalidate: inv });
  const results = useApiMutation<{ published: number }>({ invalidate: [...inv, ["exam-subs", id]], onSuccess: () => {} });
  const generate = useApiMutation({ success: "Generating the paper", invalidate: inv });
  const add = useApiMutation({ success: "Question added", invalidate: inv, onSuccess: () => setAdding(false) });
  const [adding, setAdding] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);

  if (q.isLoading) return <LoadingBlock rows={5} />;
  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />;
  const e = q.data!;
  const editable = e.status === "draft" || e.status === "review";
  const prePublish = editable || e.status === "generating";
  const tab = prePublish ? "paper" : "submissions";
  const mismatch = e.computed_total !== undefined && Math.abs(e.computed_total - e.total_marks) > 1e-6;
  const openPdf = async () => {
    setPdfBusy(true);
    try { const r = await api<{ download_url: string }>(editable ? `/examinations/${id}/generate-paper` : `/examinations/${id}/paper`, { method: editable ? "POST" : "GET" }); window.open(r.download_url, "_blank", "noopener"); } finally { setPdfBusy(false); }
  };
  return (
    <>
      <PageHeader back={<Link href="/teacher/exams" className="text-muted hover:text-ink">Examinations</Link>}
        title={<span className="flex flex-wrap items-center gap-2">{e.title}<StatusBadge status={e.status} />{e.is_demo && <SampleBadge />}</span>}
        description={`${e.subject} · ${e.total_marks} marks · ${e.duration_minutes} minutes${e.published_at ? ` · published ${fmtDate(e.published_at)}` : ""}`}
        actions={<>
          {e.questions.length > 0 && !e.is_demo && <Button variant="secondary" loading={pdfBusy} onClick={openPdf}><Download className="h-4 w-4" />{editable ? "Preview PDF" : "Question paper"}</Button>}
          {editable && mismatch && <Button variant="secondary" loading={recalc.isPending} onClick={() => recalc.mutate({ path: `/examinations/${id}/recalculate` })}>Recalculate total</Button>}
          {editable && <ConfirmButton title="Publish this paper?" body="Questions, answer keys and rubrics are locked and the rubric is approved for marking. Enrolled students can then download the paper." confirmLabel="Publish" danger={false} variant="primary" size="md" disabled={!e.questions.length || mismatch}
            onConfirm={() => publish.mutateAsync({ path: `/examinations/${id}/publish` })}>Approve and publish</ConfirmButton>}
          {e.status === "published" && <ConfirmButton title="Stop accepting submissions?" body="Students will no longer be able to upload answer sheets." confirmLabel="Close submissions" variant="secondary" size="md" onConfirm={() => close.mutateAsync({ path: `/examinations/${id}/close` })}>Close submissions</ConfirmButton>}
          {["published", "closed", "results_published"].includes(e.status) && !e.is_demo && <ConfirmButton title="Publish approved results?" body="Every answer sheet you have approved becomes visible to its student. Sheets not yet approved stay hidden; you can publish again later." confirmLabel="Publish results" danger={false} variant="primary" size="md"
            onConfirm={() => results.mutateAsync({ path: `/examinations/${id}/publish-results` }).then((r) => import("sonner").then(({ toast }) => toast.success(`${r.published} result${r.published === 1 ? "" : "s"} published`)))}>Publish results</ConfirmButton>}
          {!editable && <Button asChild variant="secondary"><Link href={`/teacher/analytics?exam=${id}`}>Analytics</Link></Button>}
        </>} />

      {e.status === "generating" && <Card className="mb-6 flex items-center gap-3 p-4 text-sm"><Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden />Writing questions, answer keys and rubrics from your material. This usually takes one to three minutes.</Card>}
      {e.generation_error && e.status === "draft" && <div className="mb-6"><ErrorState error={{ message: `Generation failed: ${e.generation_error}` }} retry={() => generate.mutate({ path: `/examinations/${id}/generate` })} /></div>}
      {!!e.config?.generation?.warnings?.length && editable && (
        <Card className="mb-6 border-warning/30 bg-warning-soft p-4 text-sm"><p className="font-medium text-warning">Check before publishing</p><ul className="mt-1 list-inside list-disc">{e.config.generation.warnings.map((w) => <li key={w}>{w}</li>)}</ul></Card>
      )}
      {mismatch && editable && <p className="mb-4 text-sm text-mark">Questions add up to {e.computed_total} marks but the paper is set to {e.total_marks}. Adjust marks or recalculate the total before publishing.</p>}

      <Tabs key={tab} defaultValue={tab}>
        <TabsList><TabsTrigger value="paper">Paper ({e.questions.length})</TabsTrigger>{!prePublish && <TabsTrigger value="submissions">Submissions</TabsTrigger>}<TabsTrigger value="calibration">Consistency</TabsTrigger></TabsList>
        <TabsContent value="paper" className="space-y-3">
          {!e.questions.length && e.status !== "generating" ? <EmptyState title="No questions yet" body="Generate the paper from your documents or add questions by hand." action={<div className="flex gap-2"><Button variant="secondary" loading={generate.isPending} onClick={() => generate.mutate({ path: `/examinations/${id}/generate` })}>Generate paper</Button><Button onClick={() => setAdding(true)}>Add question</Button></div>} />
            : e.questions.map((x) => <QuestionCard key={x.id} q={x} editable={editable} examId={id} />)}
          {editable && e.questions.length > 0 && <Button variant="secondary" onClick={() => setAdding(true)}><Plus className="h-4 w-4" />Add question</Button>}
        </TabsContent>
        {!prePublish && <TabsContent value="submissions"><Submissions examId={id} max={e.total_marks} /></TabsContent>}
        <TabsContent value="calibration"><Calibration exam={e} /></TabsContent>
      </Tabs>
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent wide title="Add question"><QuestionEditor initial={emptyQuestion()} saving={add.isPending} submitLabel="Add question" onSave={(v) => add.mutate({ path: `/examinations/${id}/questions`, json: v })} /></DialogContent>
      </Dialog>
    </>
  );
}
