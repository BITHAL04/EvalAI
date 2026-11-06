"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { QUESTION_TYPES } from "@/components/teacher/question-editor";
import { Button, Card, EmptyState, Field, Input, LoadingBlock, PageHeader, Select, Textarea } from "@/components/ui";
import { useSubjects } from "@/hooks/use-subjects";
import { ApiError, useApi, useApiQuery } from "@/lib/api";
import { cn, label } from "@/lib/utils";
import type { Exam, Material, Page } from "@/types/api";

const schema = z.object({
  title: z.string().trim().min(3, "Give the examination a title"),
  subject_id: z.string().min(1, "Choose a subject"),
  semester: z.string().optional(),
  duration_minutes: z.coerce.number().int().min(5, "At least 5 minutes").max(600),
  total_marks: z.coerce.number().positive("Enter the total marks"),
  topics: z.array(z.string()).min(1, "Choose at least one topic"),
  material_ids: z.array(z.string()),
  question_types: z.array(z.string()).min(1, "Choose at least one question type"),
  mark_distribution: z.array(z.object({ marks: z.coerce.number().positive(), count: z.coerce.number().int().min(1) })).min(1),
  difficulty: z.object({ Easy: z.coerce.number().min(0), Medium: z.coerce.number().min(0), Hard: z.coerce.number().min(0) }),
  negative_marking: z.boolean(),
  instructions: z.string(),
  generation_notes: z.string(),
  duplicate_policy: z.enum(["replace", "reject"]),
}).refine((v) => Math.abs(v.mark_distribution.reduce((s, r) => s + r.marks * r.count, 0) - v.total_marks) < 1e-6, { path: ["mark_distribution"], message: "Questions must add up to the total marks" })
  .refine((v) => v.difficulty.Easy + v.difficulty.Medium + v.difficulty.Hard > 0, { path: ["difficulty"], message: "Set a difficulty mix" });
type Form = z.input<typeof schema>;
type Out = z.output<typeof schema>;

const STEPS = ["Basics", "Content", "Structure", "Instructions"];
const PRESETS: Record<string, { Easy: number; Medium: number; Hard: number }> = { Easy: { Easy: 60, Medium: 30, Hard: 10 }, Medium: { Easy: 25, Medium: 55, Hard: 20 }, Hard: { Easy: 10, Medium: 40, Hard: 50 } };

export default function NewExam() {
  const subjects = useSubjects();
  const api = useApi();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [topicInput, setTopicInput] = useState("");
  const [busy, setBusy] = useState(false);
  const f = useForm<Form, unknown, Out>({
    resolver: zodResolver(schema),
    defaultValues: { title: "", subject_id: "", semester: "", duration_minutes: 90, total_marks: 40, topics: [], material_ids: [], question_types: ["descriptive", "analytical"],
      mark_distribution: [{ marks: 10, count: 2 }, { marks: 5, count: 4 }], difficulty: PRESETS.Medium, negative_marking: false,
      instructions: "Answer all questions.\nWrite the question number clearly before each answer.\nNumber every page of your answer booklet.", generation_notes: "", duplicate_policy: "replace" },
  });
  const rows = useFieldArray({ control: f.control, name: "mark_distribution" });
  const v = useWatch({ control: f.control }) as Form;
  const sid = v.subject_id || "";
  const topics = useApiQuery<{ items: string[] }>(["topics", sid], sid ? `/subjects/${sid}/topics` : null, { staleTime: 0, refetchOnMount: "always" });
  const docs = useApiQuery<Page<Material>>(["documents", sid, "indexed"], sid ? `/documents?subject_id=${sid}&status=indexed` : null, { staleTime: 0, refetchOnMount: "always" });
  const e = f.formState.errors;
  const sum = (v.mark_distribution ?? []).reduce((s, r) => s + Number(r.marks || 0) * Number(r.count || 0), 0);
  const fieldsByStep: (keyof Form)[][] = [["title", "subject_id", "duration_minutes"], ["topics", "material_ids"], ["total_marks", "mark_distribution", "question_types", "difficulty"], []];

  async function next() {
    if (!(await f.trigger(fieldsByStep[step]))) return;
    if (step === 0) { topics.refetch(); docs.refetch(); } // indexing may have finished since the subject was chosen
    setStep((s) => s + 1);
  }
  const toggle = (key: "topics" | "material_ids" | "question_types", val: string) => {
    const cur = (f.getValues(key) as string[]) ?? [];
    f.setValue(key, cur.includes(val) ? cur.filter((x) => x !== val) : [...cur, val], { shouldValidate: true });
  };

  async function submit(out: Out, generate: boolean) {
    setBusy(true);
    try {
      const exam = await api<Exam>("/examinations", { method: "POST", json: { ...out, semester: out.semester || null } });
      if (generate) {
        await api(`/examinations/${exam.id}/generate`, { method: "POST" });
        toast.success("Generating the paper. You can review it as soon as it is ready.");
      } else toast.success("Draft created. Add questions manually.");
      router.push(`/teacher/exams/${exam.id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create the examination");
      setBusy(false);
    }
  }

  if (subjects.isLoading) return <LoadingBlock />;
  if (!subjects.data?.items.length) return <EmptyState title="Create a subject first" action={<Button asChild><Link href="/teacher/subjects">Go to subjects</Link></Button>} />;
  return (
    <>
      <PageHeader title="Create examination" back={<Link href="/teacher/exams" className="text-muted hover:text-ink">Examinations</Link>} />
      <ol className="mb-6 flex flex-wrap gap-2" aria-label="Steps">
        {STEPS.map((s, i) => <li key={s} aria-current={i === step ? "step" : undefined} className={cn("rounded-full px-3 py-1 text-sm", i === step ? "bg-primary text-white" : i < step ? "bg-primary-soft text-primary" : "bg-paper text-muted ring-1 ring-line")}>{i + 1}. {s}</li>)}
      </ol>
      <Card className="p-6">
        <form onSubmit={(ev) => ev.preventDefault()} className="space-y-5">
          {step === 0 && (<>
            <Field label="Title" error={e.title?.message}>{(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!e.title} placeholder="Machine Learning — Mid-semester examination" {...f.register("title")} />}</Field>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Subject" error={e.subject_id?.message}>{(id, d) => <Select id={id} aria-describedby={d} {...f.register("subject_id", { onChange: () => { f.setValue("topics", []); f.setValue("material_ids", []); } })}><option value="">Choose…</option>{subjects.data!.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>}</Field>
              <Field label="Semester or class">{(id) => <Input id={id} {...f.register("semester")} />}</Field>
              <Field label="Duration (minutes)" error={e.duration_minutes?.message}>{(id, d) => <Input id={id} aria-describedby={d} type="number" {...f.register("duration_minutes")} />}</Field>
            </div>
          </>)}
          {step === 1 && (<>
            <div>
              <p className="text-sm font-medium">Topics and chapters</p>
              <p className="mb-2 text-xs text-muted">Chapters detected in your documents are listed. Add others by name.</p>
              <div className="flex flex-wrap gap-2">
                {Array.from(new Set([...(topics.data?.items ?? []), ...(v.topics ?? [])])).map((t) => (
                  <button type="button" key={t} aria-pressed={v.topics?.includes(t)} onClick={() => toggle("topics", t)} className={cn("rounded-full border px-3 py-1 text-sm", v.topics?.includes(t) ? "border-primary bg-primary-soft text-primary" : "border-line bg-paper")}>{t}</button>
                ))}
              </div>
              <div className="mt-3 flex max-w-md gap-2">
                <Input aria-label="Add a topic" value={topicInput} onChange={(x) => setTopicInput(x.target.value)} placeholder="Add a topic" onKeyDown={(x) => { if (x.key === "Enter" && topicInput.trim()) { x.preventDefault(); toggle("topics", topicInput.trim()); setTopicInput(""); } }} />
                <Button type="button" variant="secondary" disabled={!topicInput.trim()} onClick={() => { toggle("topics", topicInput.trim()); setTopicInput(""); }}>Add</Button>
              </div>
              {e.topics && <p className="mt-1 text-xs text-mark">{e.topics.message}</p>}
            </div>
            <div>
              <p className="text-sm font-medium">Reference documents</p>
              <p className="mb-2 text-xs text-muted">Leave all unticked to use every indexed document in the subject.</p>
              {docs.isLoading ? <LoadingBlock rows={1} /> : !docs.data?.items.length ? <p className="text-sm text-warning">No indexed documents yet. You can still create a draft and add questions by hand. <Link className="underline" href="/teacher/documents">Upload documents</Link></p> : (
                <div className="space-y-1">{docs.data.items.map((d) => <label key={d.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={v.material_ids?.includes(d.id)} onChange={() => toggle("material_ids", d.id)} />{d.title} <span className="text-muted">({d.chunk_count} sections)</span></label>)}</div>
              )}
            </div>
          </>)}
          {step === 2 && (<>
            <Field label="Total marks" error={e.total_marks?.message} className="max-w-48">{(id, d) => <Input id={id} aria-describedby={d} type="number" {...f.register("total_marks")} />}</Field>
            <div>
              <p className="text-sm font-medium">Mark distribution</p>
              <div className="mt-2 space-y-2">
                {rows.fields.map((r, i) => (
                  <div key={r.id} className="flex items-center gap-2 text-sm">
                    <Input aria-label={`Row ${i + 1} number of questions`} type="number" className="w-20" {...f.register(`mark_distribution.${i}.count`)} /> questions of
                    <Select aria-label={`Row ${i + 1} marks`} className="w-24" {...f.register(`mark_distribution.${i}.marks`)}>{[2, 3, 4, 5, 6, 8, 10, 12, 15, 20].map((m) => <option key={m} value={m}>{m}</option>)}</Select> marks
                    <Button type="button" variant="ghost" size="icon" aria-label={`Remove row ${i + 1}`} disabled={rows.fields.length === 1} onClick={() => rows.remove(i)}><Trash2 className="h-4 w-4" /></Button>
                  </div>
                ))}
              </div>
              <div className="mt-2 flex items-center gap-4">
                <Button type="button" size="sm" variant="secondary" onClick={() => rows.append({ marks: 5, count: 1 })}><Plus className="h-3.5 w-3.5" />Add row</Button>
                <p className={cn("text-sm tabular-nums", Math.abs(sum - Number(v.total_marks)) > 1e-6 ? "text-mark" : "text-success")}>{sum} of {String(v.total_marks)} marks allocated</p>
              </div>
              {e.mark_distribution && <p className="mt-1 text-xs text-mark">{e.mark_distribution.message ?? e.mark_distribution.root?.message}</p>}
            </div>
            <div>
              <p className="text-sm font-medium">Question types</p>
              <div className="mt-2 flex flex-wrap gap-2">{QUESTION_TYPES.map((t) => <button type="button" key={t} aria-pressed={v.question_types?.includes(t)} onClick={() => toggle("question_types", t)} className={cn("rounded-full border px-3 py-1 text-sm", v.question_types?.includes(t) ? "border-primary bg-primary-soft text-primary" : "border-line bg-paper")}>{label(t)}</button>)}</div>
              {e.question_types && <p className="mt-1 text-xs text-mark">{e.question_types.message}</p>}
            </div>
            <div>
              <p className="text-sm font-medium">Difficulty mix (%)</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {Object.keys(PRESETS).map((k) => <Button key={k} type="button" size="sm" variant="secondary" onClick={() => f.setValue("difficulty", PRESETS[k])}>Mostly {k.toLowerCase()}</Button>)}
              </div>
              <div className="mt-3 grid max-w-md grid-cols-3 gap-3">{(["Easy", "Medium", "Hard"] as const).map((k) => <Field key={k} label={k}>{(id) => <Input id={id} type="number" min={0} {...f.register(`difficulty.${k}`)} />}</Field>)}</div>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" {...f.register("negative_marking")} />Negative marking applies (printed on the paper as an instruction)</label>
          </>)}
          {step === 3 && (<>
            <Field label="General instructions" hint="One per line. Printed on the paper.">{(id, d) => <Textarea id={id} aria-describedby={d} className="min-h-32" {...f.register("instructions")} />}</Field>
            <Field label="Notes for question generation" hint="Optional, e.g. 'favour application questions about real datasets'. Never shown to students.">{(id, d) => <Textarea id={id} aria-describedby={d} {...f.register("generation_notes")} />}</Field>
            <Field label="If a student submits again">{(id) => <Select id={id} {...f.register("duplicate_policy")}><option value="replace">Replace the earlier submission until marking starts</option><option value="reject">Accept only the first submission</option></Select>}</Field>
          </>)}
          <div className="flex justify-between border-t border-line pt-5">
            <Button type="button" variant="secondary" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>Back</Button>
            {step < STEPS.length - 1 ? <Button type="button" onClick={next}>Continue</Button> : (
              <div className="flex gap-2">
                <Button type="button" variant="secondary" loading={busy} onClick={f.handleSubmit((o) => submit(o, false))}>Create empty draft</Button>
                <Button type="button" loading={busy} onClick={f.handleSubmit((o) => submit(o, true))} disabled={!docs.data?.items.length}>Generate paper</Button>
              </div>
            )}
          </div>
        </form>
      </Card>
    </>
  );
}
