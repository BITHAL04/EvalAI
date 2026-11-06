"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, FileUp, Loader2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button, Card, ConfirmButton, ErrorState, LoadingBlock, PageHeader, Progress, StatusBadge } from "@/components/ui";
import { ApiError, uploadWithProgress, useApi, useApiMutation, useApiQuery } from "@/lib/api";
import { bytes, fmtDate } from "@/lib/utils";
import type { Exam, Submission } from "@/types/api";

type ExamView = Exam & { questions: { question_number: number; question_text: string; marks: number; topic: string }[] };
const MAX_MB = 50;
const PROCESSING: Record<string, string> = {
  submitted: "Your answer sheet is queued for reading.", extracting: "Reading your handwriting page by page.", extracted: "Pages read. Marking will begin shortly.",
  evaluating: "Your answers are being evaluated.", evaluated: "Evaluated. Your teacher is reviewing the marks.", approved: "Your teacher has approved the marks. They will appear when results are published.",
  failed: "Your teacher has been asked to check your answer sheet. You do not need to do anything.",
};

function Previews({ id }: { id: string }) {
  const q = useApiQuery<{ items: { page_number: number; url: string }[] }>(["pages", id], `/submissions/${id}/pages`);
  if (q.isLoading) return <LoadingBlock rows={1} />;
  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
      {/* eslint-disable-next-line @next/next/no-img-element -- signed preview URLs */}
      {q.data?.items.map((p) => <figure key={p.page_number}><img src={p.url} alt={`Page ${p.page_number}`} className="aspect-[1/1.41] w-full rounded border border-line object-cover" /><figcaption className="mt-1 text-center text-xs text-muted">Page {p.page_number}</figcaption></figure>)}
    </div>
  );
}

export default function StudentExam() {
  const { id } = useParams<{ id: string }>();
  const api = useApi();
  const qc = useQueryClient();
  const exam = useApiQuery<ExamView>(["exam", id], `/examinations/${id}`);
  const list = useApiQuery<{ items: Exam[] }>(["exams", "student"], "/examinations?limit=100");
  const mine = list.data?.items.find((e) => e.id === id)?.my_submission ?? null;
  const [draft, setDraft] = useState<Submission | null>(null);
  const sub = draft ?? (mine ? ({ ...mine, examination_id: id } as unknown as Submission) : null);
  const status = useApiQuery<{ status: string; extraction: { pages_done: number; pages_total: number } | null; questions_total: number; questions_evaluated: number }>(["sub-status", sub?.id], sub?.submitted_at ? `/submissions/${sub.id}/status` : null, {
    refetchInterval: (x) => (["submitted", "extracting", "extracted", "evaluating"].includes(x.state.data?.status ?? "") ? 4000 : false),
  });
  const input = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const confirm = useApiMutation<Submission>({ success: "Submitted. You will be notified when your result is published.", onSuccess: (s) => { setDraft(s); qc.invalidateQueries({ queryKey: ["exams", "student"] }); } });

  async function upload(f: File) {
    setError(null);
    if (!/\.pdf$/i.test(f.name) || (f.type && f.type !== "application/pdf")) return setError("Combine your pages into a single PDF, then upload it.");
    if (f.size > MAX_MB * 1024 * 1024) return setError(`The file is ${bytes(f.size)}. The limit is ${MAX_MB} MB; try scanning at a lower resolution.`);
    try {
      setProgress(0);
      const s = await api<Submission & { upload_url: string; method: string; headers: Record<string, string> }>("/submissions", { method: "POST", json: { examination_id: id, filename: f.name, size_bytes: f.size } });
      await uploadWithProgress(s.upload_url, s.method, s.headers, f, setProgress);
      const ok = await api<Submission>(`/submissions/${s.id}/upload`, { method: "POST" });
      setDraft(ok);
      toast.success(`Uploaded ${ok.page_count} pages. Check them, then submit.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed. Try again.");
    } finally { setProgress(null); }
  }

  if (exam.isLoading || list.isLoading) return <LoadingBlock rows={5} />;
  if (exam.error) return <ErrorState error={exam.error} retry={exam.refetch} />;
  const e = exam.data!;
  const open = e.status === "published" && (!e.submission_deadline || new Date(e.submission_deadline) > new Date());
  const submitted = !!sub?.submitted_at;
  const canReplace = submitted && e.duplicate_policy === "replace" && open && ["submitted", "extracting", "extracted"].includes(status.data?.status ?? sub?.status ?? "");
  return (
    <>
      <PageHeader back={<Link href="/student/exams" className="text-muted hover:text-ink">Examinations</Link>} title={e.title}
        description={`${e.subject} · ${e.total_marks} marks · ${e.duration_minutes} minutes${e.submission_deadline ? ` · due ${fmtDate(e.submission_deadline)}` : ""}`}
        actions={<Button variant="secondary" onClick={async () => { try { const r = await api<{ download_url: string }>(`/examinations/${id}/paper`); window.open(r.download_url, "_blank", "noopener"); } catch (err) { toast.error((err as Error).message); } }}><Download className="h-4 w-4" />Download question paper</Button>} />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <Card className="p-5">
          <h2 className="font-semibold">Instructions</h2>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm">{e.instructions.split("\n").filter(Boolean).map((l) => <li key={l}>{l}</li>)}</ul>
          <h3 className="mt-5 text-sm font-semibold">Questions</h3>
          <ol className="mt-2 space-y-2 text-sm">{e.questions.map((q) => <li key={q.question_number} className="flex gap-3"><span className="font-semibold text-primary">Q{q.question_number}</span><span className="flex-1">{q.question_text}</span><span className="text-muted">[{q.marks}]</span></li>)}</ol>
        </Card>
        <div className="space-y-4">
          {submitted ? (
            <Card className="p-5">
              <div className="flex items-start justify-between gap-3"><h2 className="flex items-center gap-2 font-semibold"><CheckCircle2 className="h-5 w-5 text-success" aria-hidden />Submitted</h2><StatusBadge status={status.data?.status ?? sub!.status} /></div>
              <p className="mt-1 text-sm text-muted">{fmtDate(sub!.submitted_at)} · version {sub!.version}</p>
              <p className="mt-4 text-sm">{PROCESSING[status.data?.status ?? sub!.status] ?? ""}</p>
              {status.data?.status === "extracting" && status.data.extraction && <div className="mt-3"><Progress value={Math.round((status.data.extraction.pages_done / Math.max(1, status.data.extraction.pages_total)) * 100)} label="Pages read" /></div>}
              {status.data?.status === "evaluating" && <p className="mt-2 text-sm text-muted">{status.data.questions_evaluated} of {status.data.questions_total} answers evaluated</p>}
              <p className="mt-4 text-xs text-muted">Marks are only shown after your teacher approves and publishes them.</p>
              <div className="mt-4"><Previews id={sub!.id} /></div>
              {canReplace && <Button className="mt-4" variant="secondary" onClick={() => input.current?.click()}>Replace with a new upload</Button>}
            </Card>
          ) : !open ? (
            <Card className="p-5"><p className="text-sm">This examination is no longer accepting submissions.</p></Card>
          ) : (
            <Card className="p-5">
              <h2 className="font-semibold">Upload your answer sheet</h2>
              <ol className="mt-2 list-inside list-decimal space-y-1 text-sm text-muted">
                <li>Write your answers in your notebook, starting each with its question number.</li>
                <li>Number every page, then scan or photograph them in order with good light.</li>
                <li>Combine the pages into one PDF (most phone scanner apps do this) and upload it below.</li>
              </ol>
              {sub && sub.status === "uploaded" ? (
                <div className="mt-5">
                  <p className="mb-3 text-sm">Check that every page is here, upright and readable. <span className="text-muted">{sub.page_count} pages</span></p>
                  <Previews id={sub.id} />
                  <div className="mt-5 flex flex-wrap gap-2">
                    <ConfirmButton title="Submit this answer sheet?" body={e.duplicate_policy === "reject" ? "This examination accepts one submission only. You cannot change it afterwards." : "You can replace it until marking starts."} confirmLabel="Submit answer sheet" danger={false} variant="primary" size="md"
                      onConfirm={() => confirm.mutateAsync({ path: `/submissions/${sub.id}/process` })}>Submit answer sheet</ConfirmButton>
                    <Button variant="secondary" onClick={() => input.current?.click()}>Upload a different file</Button>
                  </div>
                </div>
              ) : (
                <div className="mt-5 rounded-[var(--radius-card)] border-2 border-dashed border-line p-8 text-center"
                  onDragOver={(x) => x.preventDefault()} onDrop={(x) => { x.preventDefault(); const f = x.dataTransfer.files[0]; if (f) { setFile(f); upload(f); } }}>
                  <FileUp className="mx-auto h-6 w-6 text-muted" aria-hidden />
                  <p className="mt-2 text-sm">Drop your PDF here, or</p>
                  <Button className="mt-3" onClick={() => input.current?.click()} loading={progress !== null}>Choose PDF</Button>
                  <p className="mt-2 text-xs text-muted">One PDF, up to {MAX_MB} MB</p>
                </div>
              )}
              {progress !== null && <div className="mt-4"><Progress value={progress} label="Upload progress" /><p className="mt-1 flex items-center gap-1.5 text-xs text-muted">{progress < 100 ? `Uploading ${file?.name ?? ""}… ${progress}%` : <><Loader2 className="h-3 w-3 animate-spin" />Preparing page previews…</>}</p></div>}
              {error && <div className="mt-4"><ErrorState error={{ message: error }} retry={file ? () => upload(file) : undefined} /></div>}
            </Card>
          )}
          <input ref={input} type="file" accept="application/pdf,.pdf" className="sr-only" aria-label="Answer sheet PDF" onChange={(x) => { const f = x.target.files?.[0]; if (f) { setFile(f); setDraft(null); upload(f); } x.target.value = ""; }} />
        </div>
      </div>
    </>
  );
}
