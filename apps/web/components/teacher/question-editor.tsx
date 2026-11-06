"use client";

import { useState } from "react";
import { Button, Field, Input, Select, Textarea } from "@/components/ui";
import { label } from "@/lib/utils";
import { RubricEditor, rubricValid, type CriterionDraft } from "./rubric-editor";

export const QUESTION_TYPES = ["short_answer", "descriptive", "long_answer", "analytical", "application", "case_study", "derivation", "diagram"];
export type QuestionDraft = { question_text: string; topic: string; difficulty: string; question_type: string; marks: number; expected_answer: string; expected_concepts: string[]; rubric: CriterionDraft[] };

export const emptyQuestion = (marks = 5): QuestionDraft => ({
  question_text: "", topic: "", difficulty: "Medium", question_type: "descriptive", marks, expected_answer: "", expected_concepts: [],
  rubric: [{ criterion: "Conceptual correctness", category: "conceptual_correctness", max_marks: marks * 0.6, expected_evidence: "" }, { criterion: "Coverage", category: "coverage", max_marks: marks * 0.4, expected_evidence: "" }],
});

export function QuestionEditor({ initial, onSave, saving, submitLabel, lockType }: { initial: QuestionDraft; onSave: (q: QuestionDraft) => void; saving?: boolean; submitLabel: string; lockType?: boolean }) {
  const [q, setQ] = useState(initial);
  const [concepts, setConcepts] = useState(initial.expected_concepts.join("\n"));
  const [touched, setTouched] = useState(false);
  const errors = {
    text: q.question_text.trim().length < 10 ? "Write at least 10 characters" : "",
    topic: q.topic.trim().length < 2 ? "Enter a topic" : "",
    answer: q.expected_answer.trim().length < 3 ? "Write the model answer" : "",
    rubric: rubricValid(q.rubric, q.marks) ? "" : "Every criterion needs a name, and the criteria must add up to the question's marks",
  };
  const ok = !Object.values(errors).some(Boolean);
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); setTouched(true); if (ok) onSave({ ...q, expected_concepts: concepts.split("\n").map((s) => s.trim()).filter(Boolean) }); }}>
      <Field label="Question" error={touched ? errors.text : ""}>{(id, d) => <Textarea id={id} aria-describedby={d} aria-invalid={touched && !!errors.text} value={q.question_text} onChange={(e) => setQ({ ...q, question_text: e.target.value })} />}</Field>
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Topic" error={touched ? errors.topic : ""} className="sm:col-span-2">{(id, d) => <Input id={id} aria-describedby={d} value={q.topic} onChange={(e) => setQ({ ...q, topic: e.target.value })} />}</Field>
        <Field label="Difficulty">{(id) => <Select id={id} value={q.difficulty} onChange={(e) => setQ({ ...q, difficulty: e.target.value })}>{["Easy", "Medium", "Hard"].map((d) => <option key={d}>{d}</option>)}</Select>}</Field>
        <Field label="Marks">{(id) => <Input id={id} type="number" min="0.5" step="0.5" value={q.marks} onChange={(e) => setQ({ ...q, marks: Number(e.target.value) })} />}</Field>
      </div>
      {!lockType && <Field label="Question type">{(id) => <Select id={id} value={q.question_type} onChange={(e) => setQ({ ...q, question_type: e.target.value })}>{QUESTION_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}</Select>}</Field>}
      <Field label="Model answer" error={touched ? errors.answer : ""}>{(id, d) => <Textarea id={id} aria-describedby={d} className="min-h-28" value={q.expected_answer} onChange={(e) => setQ({ ...q, expected_answer: e.target.value })} />}</Field>
      <Field label="Expected concepts" hint="One per line. Used to check coverage; wording in answers can differ.">{(id, d) => <Textarea id={id} aria-describedby={d} value={concepts} onChange={(e) => setConcepts(e.target.value)} />}</Field>
      <div>
        <p className="mb-2 text-sm font-medium">Marking rubric</p>
        <RubricEditor value={q.rubric} onChange={(rubric) => setQ({ ...q, rubric })} marks={q.marks} />
        {touched && errors.rubric && <p className="mt-2 text-xs text-mark">{errors.rubric}</p>}
      </div>
      <div className="flex justify-end"><Button type="submit" loading={saving}>{submitLabel}</Button></div>
    </form>
  );
}
