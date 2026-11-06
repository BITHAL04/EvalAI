"use client";

import { Plus, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { emptyQuestion, QuestionEditor, QUESTION_TYPES, type QuestionDraft } from "@/components/teacher/question-editor";
import { Badge, Button, Card, ConfirmButton, Dialog, DialogContent, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Select } from "@/components/ui";
import { useSubjects } from "@/hooks/use-subjects";
import { useApiMutation, useApiQuery } from "@/lib/api";
import { label } from "@/lib/utils";
import type { Material, Page, SourceRef } from "@/types/api";

type BankItem = QuestionDraft & { id: string; origin: string; source_references: SourceRef[]; subject_id: string };

function Generate({ subjectId, onDone }: { subjectId: string; onDone: () => void }) {
  const topics = useApiQuery<{ items: string[] }>(["topics", subjectId], `/subjects/${subjectId}/topics`);
  const docs = useApiQuery<Page<Material>>(["documents", subjectId], `/documents?subject_id=${subjectId}&status=indexed`);
  const [topic, setTopic] = useState("");
  const [cfg, setCfg] = useState({ count: 3, marks: 5, difficulty: "Medium", question_type: "descriptive" });
  const gen = useApiMutation<{ items: BankItem[]; warnings: string[] }>({ invalidate: [["bank", subjectId]], onSuccess: (d) => { onDone(); toast.success(`${d.items.length} questions added`); d.warnings.forEach((w) => toast.warning(w)); } });
  if (docs.data && !docs.data.items.length) return <p className="text-sm text-muted">Index at least one document for this subject first. Questions are written only from your material.</p>;
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); gen.mutate({ path: "/questions/generate", json: { subject_id: subjectId, topics: [topic.trim()], ...cfg } }); }}>
      <Field label="Topic" hint="Chapters found in your documents are suggested.">{(id, d) => (<><Input id={id} aria-describedby={d} list="topic-list" value={topic} onChange={(e) => setTopic(e.target.value)} required minLength={2} /><datalist id="topic-list">{topics.data?.items.map((t) => <option key={t} value={t} />)}</datalist></>)}</Field>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="How many">{(id) => <Input id={id} type="number" min={1} max={10} value={cfg.count} onChange={(e) => setCfg({ ...cfg, count: Number(e.target.value) })} />}</Field>
        <Field label="Marks each">{(id) => <Input id={id} type="number" min={1} value={cfg.marks} onChange={(e) => setCfg({ ...cfg, marks: Number(e.target.value) })} />}</Field>
        <Field label="Difficulty">{(id) => <Select id={id} value={cfg.difficulty} onChange={(e) => setCfg({ ...cfg, difficulty: e.target.value })}>{["Easy", "Medium", "Hard"].map((d) => <option key={d}>{d}</option>)}</Select>}</Field>
        <Field label="Type">{(id) => <Select id={id} value={cfg.question_type} onChange={(e) => setCfg({ ...cfg, question_type: e.target.value })}>{QUESTION_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}</Select>}</Field>
      </div>
      {gen.isPending && <p className="text-sm text-muted">Reading your material and writing questions. This can take a minute.</p>}
      <div className="flex justify-end"><Button type="submit" loading={gen.isPending} disabled={topic.trim().length < 2}><Sparkles className="h-4 w-4" />Generate questions</Button></div>
    </form>
  );
}

export default function QuestionBank() {
  const subjects = useSubjects();
  const [subject, setSubject] = useState("");
  const [topic, setTopic] = useState("");
  const sid = subject || subjects.data?.items[0]?.id || "";
  const bank = useApiQuery<Page<BankItem>>(["bank", sid, topic], sid ? `/questions?subject_id=${sid}&limit=100${topic ? `&topic=${encodeURIComponent(topic)}` : ""}` : null);
  const [dialog, setDialog] = useState<null | "new" | "generate" | BankItem>(null);
  const save = useApiMutation({ success: "Question saved", invalidate: [["bank", sid]], onSuccess: () => setDialog(null) });
  const del = useApiMutation({ success: "Question deleted", invalidate: [["bank", sid]] });
  if (subjects.isLoading) return <LoadingBlock />;
  if (!subjects.data?.items.length) return <><PageHeader title="Question bank" /><EmptyState title="Create a subject first" /></>;
  const topics = Array.from(new Set((bank.data?.items ?? []).map((q) => q.topic)));
  return (
    <>
      <PageHeader title="Question bank" description="Reusable questions with model answers and rubrics."
        actions={<>
          <Select aria-label="Subject" value={sid} onChange={(e) => { setSubject(e.target.value); setTopic(""); }} className="w-56">{subjects.data.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>
          <Button variant="secondary" onClick={() => setDialog("generate")}><Sparkles className="h-4 w-4" />Generate</Button>
          <Button onClick={() => setDialog("new")}><Plus className="h-4 w-4" />Add question</Button>
        </>} />
      {topics.length > 1 && !topic && (
        <div className="mb-4 flex flex-wrap gap-2">{topics.map((t) => <button key={t} onClick={() => setTopic(t)} className="rounded-full border border-line bg-paper px-3 py-1 text-sm hover:border-primary">{t}</button>)}</div>
      )}
      {topic && <button onClick={() => setTopic("")} className="mb-4 text-sm text-primary hover:underline">Showing {topic} · show all topics</button>}
      {bank.isLoading ? <LoadingBlock /> : bank.error ? <ErrorState error={bank.error} retry={bank.refetch} /> : !bank.data!.items.length ? (
        <EmptyState title="No questions yet" body="Add your own or generate some from indexed documents." />
      ) : (
        <div className="space-y-3">
          {bank.data!.items.map((q) => (
            <Card key={q.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{q.question_text}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5"><Badge>{q.topic}</Badge><Badge>{q.difficulty}</Badge><Badge>{label(q.question_type)}</Badge><Badge tone="primary">{q.marks} marks</Badge>{q.origin === "ai" && <Badge tone="primary">AI generated</Badge>}{q.origin === "seed" && <Badge>Sample data</Badge>}</div>
                  {q.source_references.length > 0 && <p className="mt-2 text-xs text-muted">Source: {q.source_references.map((r) => `${r.material_title} p.${r.page_start ?? "?"}`).join("; ")}</p>}
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="secondary" onClick={() => setDialog(q)}>Edit</Button>
                  <ConfirmButton title="Delete this question?" body="It is removed from the bank. Papers that already use it are not affected." confirmLabel="Delete question" variant="ghost" onConfirm={() => del.mutateAsync({ path: `/questions/${q.id}`, method: "DELETE" })}><Trash2 className="h-3.5 w-3.5" /><span className="sr-only">Delete</span></ConfirmButton>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      <Dialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)}>
        {dialog === "generate" ? <DialogContent title="Generate questions" description="Questions are written from this subject's indexed documents, with rubrics."><Generate subjectId={sid} onDone={() => setDialog(null)} /></DialogContent>
          : dialog ? (
            <DialogContent wide title={dialog === "new" ? "Add question" : "Edit question"}>
              <QuestionEditor initial={dialog === "new" ? emptyQuestion() : { ...dialog, rubric: dialog.rubric.length ? dialog.rubric : emptyQuestion(dialog.marks).rubric }} saving={save.isPending} submitLabel="Save question"
                onSave={(v) => save.mutate({ path: dialog === "new" ? "/questions" : `/questions/${dialog.id}`, method: dialog === "new" ? "POST" : "PUT", json: { ...v, subject_id: sid } })} />
            </DialogContent>
          ) : null}
      </Dialog>
    </>
  );
}
