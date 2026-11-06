"use client";

import { Bot, Loader2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { PageViewer } from "@/components/page-viewer";
import { Badge, Button, Card, ConfirmButton, ErrorState, Field, Input, LoadingBlock, Marks, PageHeader, Select, StatusBadge, Textarea } from "@/components/ui";
import { useApiMutation, useApiQuery } from "@/lib/api";
import { fmtDate, label } from "@/lib/utils";
import type { Challenge } from "@/types/api";

export default function ChallengeDetail() {
  const { id } = useParams<{ id: string }>();
  const q = useApiQuery<Challenge>(["challenge", id], `/challenges/${id}`, { refetchInterval: (x) => (["submitted", "under_ai_review"].includes(x.state.data?.status ?? "") ? 3000 : false) });
  const inv = [["challenge", id], ["challenges"]];
  const decide = useApiMutation({ success: "Decision recorded. The student has been notified.", invalidate: inv });
  const finalize = useApiMutation({ success: "Challenge resolved", invalidate: inv });
  const rerun = useApiMutation({ success: "AI review restarted", invalidate: inv });
  const [decision, setDecision] = useState("partially_accepted");
  const [marks, setMarks] = useState<string>("");
  const [reason, setReason] = useState("");
  const [rubricNote, setRubricNote] = useState("");
  if (q.isLoading) return <LoadingBlock rows={6} />;
  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />;
  const c = q.data!;
  const ai = c.ai_reviews?.[c.ai_reviews.length - 1];
  const pending = c.status === "pending_teacher_review";
  const m = marks === "" ? (ai?.suggested_marks ?? c.original_marks) : Number(marks);
  const invalid = decision !== "rejected" && (m < 0 || m > c.max_marks || (decision === "accepted" && m === c.original_marks));
  return (
    <>
      <PageHeader back={<Link href="/teacher/challenges" className="text-muted hover:text-ink">Challenges</Link>}
        title={<span className="flex flex-wrap items-center gap-2">Q{c.question_number} · {c.student}<StatusBadge status={c.status} /></span>}
        description={`${label(c.category)}${c.disputed_criterion ? ` · disputes "${c.disputed_criterion}"` : ""} · raised ${fmtDate(c.created_at)} · rubric v${c.rubric_version}`} />
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-4">
          <Card className="p-5">
            <p className="text-sm text-muted">Question</p><p className="mt-1">{c.question_text}</p>
            <p className="mt-4 text-sm text-muted">Student&apos;s argument</p><p className="mt-1 whitespace-pre-wrap">{c.explanation}</p>
            {c.evidence.length > 0 && <><p className="mt-4 text-sm text-muted">Supporting evidence</p><ul className="mt-1 list-inside list-disc text-sm">{c.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul></>}
          </Card>
          {c.evaluation && (
            <Card className="p-5">
              <div className="flex justify-between"><p className="font-semibold">Current evaluation</p><Marks got={c.evaluation.marks_awarded} max={c.evaluation.max_marks} /></div>
              <ul className="mt-3 divide-y divide-line text-sm">{c.evaluation.criteria.map((x) => <li key={x.criterion_id} className="flex justify-between gap-3 py-2"><span><span className={x.criterion === c.disputed_criterion ? "font-semibold text-primary" : "font-medium"}>{x.criterion}</span><br /><span className="text-muted">{x.reason}</span></span><Marks got={x.awarded_marks} max={x.max_marks} /></li>)}</ul>
              <p className="mt-3 text-sm text-muted">Recognised answer</p>
              <p className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap rounded bg-canvas p-3 font-mono text-[13px]">{c.evaluation.answer_text || "(none)"}</p>
            </Card>
          )}
          {c.evaluation && <PageViewer submissionId={c.evaluation.submission_id} focus={c.evaluation.pages[0]} />}
        </div>
        <div className="space-y-4">
          <Card className="p-5">
            <p className="flex items-center gap-2 font-semibold"><Bot className="h-4 w-4 text-primary" aria-hidden />AI recommendation</p>
            {["submitted", "under_ai_review"].includes(c.status) ? <p className="mt-3 flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" />Reviewing the argument against the key, rubric, answer and sources…</p>
              : !ai ? <p className="mt-3 text-sm text-muted">No AI review is available (the AI service was unavailable). You can decide without it{pending ? " or run it again" : ""}.</p> : (
              <div className="mt-3 space-y-3 text-sm">
                <div className="flex flex-wrap items-center gap-2"><Badge tone="primary">{label(ai.recommendation)}</Badge>{ai.suggested_marks !== null && <span>Suggested <Marks got={ai.suggested_marks} max={c.max_marks} /></span>}<span className="text-muted">confidence {Math.round(ai.confidence * 100)}%</span>{ai.escalated && <Badge tone="warning">Needs your judgement</Badge>}</div>
                <p>{ai.reasoning}</p>
                {ai.detail.analysis && <p className="text-muted">Claim: {ai.detail.analysis.claim_summary} ({label(ai.detail.analysis.claim_type)})</p>}
                {ai.detail.validity && <p className="text-muted">Validity: {ai.detail.validity.reasoning}</p>}
                {ai.detail.rubric_change_suggested && <p className="text-muted">Suggested rubric change: {ai.detail.rubric_change_suggested}</p>}
                {!!ai.detail.sources?.length && <p className="text-xs text-muted">Sources checked: {ai.detail.sources.map((s) => `${s.material_title} p.${s.page_start ?? "?"}`).join("; ")}</p>}
              </div>
            )}
            {pending && <Button className="mt-4" size="sm" variant="secondary" loading={rerun.isPending} onClick={() => rerun.mutate({ path: `/challenges/${id}/review` })}>Run AI review again</Button>}
          </Card>
          {pending && (
            <Card className="p-5">
              <p className="font-semibold">Your decision</p>
              <div className="mt-4 space-y-4">
                <Field label="Decision">{(fid) => <Select id={fid} value={decision} onChange={(e) => setDecision(e.target.value)}><option value="accepted">Accept</option><option value="partially_accepted">Partially accept</option><option value="rejected">Reject</option></Select>}</Field>
                {decision !== "rejected" && <Field label={`Revised marks for this question (0–${c.max_marks})`} hint={`Currently ${c.original_marks}. The change is applied to the disputed criterion first.`} error={invalid ? "Enter marks within range that differ from the original" : undefined}>{(fid, d) => <Input id={fid} aria-describedby={d} type="number" step="0.25" min={0} max={c.max_marks} value={marks === "" ? String(m) : marks} onChange={(e) => setMarks(e.target.value)} />}</Field>}
                <Field label="Reason (shown to the student)">{(fid) => <Textarea id={fid} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
                {decision !== "rejected" && <Field label="Update the rubric (optional)" hint="Adds an accepted alternative to the disputed criterion as a new rubric version for future marking.">{(fid, d) => <Input id={fid} aria-describedby={d} value={rubricNote} onChange={(e) => setRubricNote(e.target.value)} />}</Field>}
                <ConfirmButton title="Record this decision?" body={decision === "rejected" ? "Marks stay as they are." : `Marks for this question change from ${c.original_marks} to ${m}. The result, topic analysis and audit history update.`} confirmLabel="Record decision" danger={false} variant="primary" size="md" disabled={reason.trim().length < 5 || invalid}
                  onConfirm={() => decide.mutateAsync({ path: `/challenges/${id}/decision`, json: { decision, revised_marks: decision === "rejected" ? null : m, reason, rubric_note: rubricNote || null } })}>Record decision</ConfirmButton>
              </div>
            </Card>
          )}
          {c.decisions.map((d, i) => (
            <Card key={i} className="p-5 text-sm">
              <div className="flex justify-between"><p className="font-semibold">{label(d.decision)}</p><span>{d.original_marks} → <Marks got={d.revised_marks} max={c.max_marks} /></span></div>
              <p className="mt-1">{d.reason}</p><p className="mt-1 text-xs text-muted">{fmtDate(d.decided_at)}</p>
              {["accepted", "partially_accepted", "rejected"].includes(c.status) && <Button className="mt-3" size="sm" loading={finalize.isPending} onClick={() => finalize.mutate({ path: `/challenges/${id}/finalize` })}>Mark as resolved</Button>}
            </Card>
          ))}
          {!!c.audit?.length && (
            <Card className="p-5"><p className="font-semibold">Audit history</p>
              <ol className="mt-3 space-y-2 text-sm">{c.audit.map((a, i) => <li key={i} className="flex justify-between gap-3"><span>{label(a.action.replace("challenge.", ""))} <span className="text-muted">by {a.actor_type}</span></span><span className="text-xs text-muted">{fmtDate(a.created_at)}</span></li>)}</ol>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
