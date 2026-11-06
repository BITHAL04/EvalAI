"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus, Trash2, Users } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { useApiMutation, useApiQuery } from "@/lib/api";
import type { Page, Subject } from "@/types/api";
import { Button, Card, ConfirmButton, Dialog, DialogContent, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Textarea } from "./ui";

const schema = z.object({
  name: z.string().trim().min(2, "Enter a subject name"),
  code: z.string().trim().min(2, "Enter a short code, e.g. ML301").max(40),
  semester: z.string().max(40).optional(),
  description: z.string().optional(),
});
type Form = z.infer<typeof schema>;

function SubjectForm({ initial, onDone }: { initial?: Subject; onDone: () => void }) {
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { name: initial?.name ?? "", code: initial?.code ?? "", semester: initial?.semester ?? "", description: initial?.description ?? "" } });
  const save = useApiMutation({ success: initial ? "Subject saved" : "Subject created", invalidate: [["subjects"]], onSuccess: onDone });
  const e = f.formState.errors;
  return (
    <form className="space-y-4" onSubmit={f.handleSubmit((v) => save.mutate({ path: initial ? `/subjects/${initial.id}` : "/subjects", method: initial ? "PUT" : "POST", json: { ...v, semester: v.semester || null } }))}>
      <Field label="Name" error={e.name?.message}>{(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!e.name} {...f.register("name")} />}</Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Code" error={e.code?.message}>{(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!e.code} {...f.register("code")} />}</Field>
        <Field label="Semester or class">{(id) => <Input id={id} {...f.register("semester")} />}</Field>
      </div>
      <Field label="Description">{(id) => <Textarea id={id} {...f.register("description")} />}</Field>
      <div className="flex justify-end"><Button type="submit" loading={save.isPending}>{initial ? "Save subject" : "Create subject"}</Button></div>
    </form>
  );
}

function Enrollment({ subject }: { subject: Subject }) {
  const enrolled = useApiQuery<{ items: { id: string; email: string; full_name: string }[] }>(["enrollments", subject.id], `/subjects/${subject.id}/enrollments`);
  const students = useApiQuery<Page<{ id: string; email: string; full_name: string; roll_number: string | null }>>(["users", "student"], "/users?role=student&limit=200");
  const add = useApiMutation({ success: "Students enrolled", invalidate: [["enrollments", subject.id], ["subjects"]] });
  const remove = useApiMutation({ success: "Student removed", invalidate: [["enrollments", subject.id], ["subjects"]] });
  const [picked, setPicked] = useState<string[]>([]);
  if (enrolled.isLoading || students.isLoading) return <LoadingBlock />;
  if (enrolled.error || students.error) return <ErrorState error={enrolled.error ?? students.error} />;
  const inSubject = new Set(enrolled.data!.items.map((s) => s.id));
  const available = students.data!.items.filter((s) => !inSubject.has(s.id));
  return (
    <div className="space-y-5">
      <div>
        <p className="mb-2 text-sm font-medium">Enrolled ({enrolled.data!.items.length})</p>
        {enrolled.data!.items.length ? (
          <ul className="max-h-48 divide-y divide-line overflow-y-auto rounded-[var(--radius-control)] border border-line">
            {enrolled.data!.items.map((s) => (
              <li key={s.id} className="flex items-center justify-between px-3 py-2 text-sm">
                <span>{s.full_name || s.email}</span>
                <Button size="sm" variant="ghost" onClick={() => remove.mutate({ path: `/subjects/${subject.id}/enrollments/${s.id}`, method: "DELETE" })}>Remove</Button>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted">No students yet.</p>}
      </div>
      <div>
        <p className="mb-2 text-sm font-medium">Add students</p>
        {available.length ? (
          <>
            <fieldset className="max-h-48 space-y-1 overflow-y-auto rounded-[var(--radius-control)] border border-line p-2">
              <legend className="sr-only">Students to enrol</legend>
              {available.map((s) => (
                <label key={s.id} className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-canvas">
                  <input type="checkbox" checked={picked.includes(s.id)} onChange={(e) => setPicked((p) => (e.target.checked ? [...p, s.id] : p.filter((x) => x !== s.id)))} />
                  {s.full_name || s.email} {s.roll_number && <span className="text-muted">({s.roll_number})</span>}
                </label>
              ))}
            </fieldset>
            <Button className="mt-3" disabled={!picked.length} loading={add.isPending} onClick={() => add.mutate({ path: `/subjects/${subject.id}/enrollments`, json: { user_ids: picked } }, { onSuccess: () => setPicked([]) })}>
              Enrol {picked.length || ""} selected
            </Button>
          </>
        ) : <p className="text-sm text-muted">Every student in your institution is enrolled. An administrator can invite more.</p>}
      </div>
    </div>
  );
}

export function SubjectsManager() {
  const q = useApiQuery<Page<Subject>>(["subjects"], "/subjects?limit=100");
  const del = useApiMutation({ success: "Subject deleted", invalidate: [["subjects"]] });
  const [dialog, setDialog] = useState<{ kind: "new" | "edit" | "enroll"; subject?: Subject } | null>(null);
  return (
    <>
      <PageHeader title="Subjects" description="Each subject holds its own documents, question bank, examinations and enrolled students." actions={<Button onClick={() => setDialog({ kind: "new" })}><Plus className="h-4 w-4" />New subject</Button>} />
      {q.isLoading ? <LoadingBlock /> : q.error ? <ErrorState error={q.error} retry={q.refetch} /> : !q.data!.items.length ? (
        <EmptyState title="No subjects yet" body="Create a subject, then upload its course material." action={<Button onClick={() => setDialog({ kind: "new" })}>Create subject</Button>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {q.data!.items.map((s) => (
            <Card key={s.id} className="flex flex-col p-5">
              <p className="text-xs font-medium text-muted">{s.code}{s.semester ? ` · Semester ${s.semester}` : ""}</p>
              <h2 className="mt-1 text-lg font-semibold">{s.name}</h2>
              {s.description && <p className="mt-1 line-clamp-2 text-sm text-muted">{s.description}</p>}
              <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
                {[["Students", s.students], ["Documents", s.documents], ["Exams", s.examinations]].map(([k, v]) => <div key={k as string}><dt className="text-muted">{k}</dt><dd className="font-semibold tabular-nums">{v ?? 0}</dd></div>)}
              </dl>
              <div className="mt-5 flex gap-2 border-t border-line pt-4">
                <Button size="sm" variant="secondary" onClick={() => setDialog({ kind: "enroll", subject: s })}><Users className="h-3.5 w-3.5" />Students</Button>
                <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: "edit", subject: s })} aria-label={`Edit ${s.name}`}><Pencil className="h-3.5 w-3.5" /></Button>
                <div className="ml-auto">
                  <ConfirmButton title={`Delete ${s.name}?`} body="Its documents and question bank are removed too. Subjects with examinations cannot be deleted." confirmLabel="Delete subject" variant="ghost"
                    onConfirm={() => del.mutateAsync({ path: `/subjects/${s.id}`, method: "DELETE" })}><Trash2 className="h-3.5 w-3.5" /><span className="sr-only">Delete {s.name}</span></ConfirmButton>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      <Dialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)}>
        {dialog?.kind === "enroll" && dialog.subject ? (
          <DialogContent title={`Students in ${dialog.subject.name}`}><Enrollment subject={dialog.subject} /></DialogContent>
        ) : dialog ? (
          <DialogContent title={dialog.kind === "new" ? "New subject" : "Edit subject"}><SubjectForm initial={dialog.subject} onDone={() => setDialog(null)} /></DialogContent>
        ) : null}
      </Dialog>
    </>
  );
}
