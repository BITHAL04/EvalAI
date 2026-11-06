"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button, Input, Select, Textarea } from "@/components/ui";
import { label } from "@/lib/utils";

export const CATEGORIES = ["conceptual_correctness", "relevance", "coverage", "explanation_depth", "technical_accuracy", "logical_reasoning", "examples", "diagram", "mathematical", "organization"];
export type CriterionDraft = { criterion: string; category: string; max_marks: number; expected_evidence: string };

export function RubricEditor({ value, onChange, marks }: { value: CriterionDraft[]; onChange: (v: CriterionDraft[]) => void; marks: number }) {
  const total = value.reduce((s, c) => s + (Number(c.max_marks) || 0), 0);
  const set = (i: number, patch: Partial<CriterionDraft>) => onChange(value.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  return (
    <div className="space-y-3">
      {value.map((c, i) => (
        <fieldset key={i} className="grid gap-2 rounded-[var(--radius-control)] border border-line p-3 sm:grid-cols-[1fr_180px_90px_auto]">
          <legend className="sr-only">Criterion {i + 1}</legend>
          <Input aria-label={`Criterion ${i + 1} name`} value={c.criterion} onChange={(e) => set(i, { criterion: e.target.value })} placeholder="Criterion" />
          <Select aria-label={`Criterion ${i + 1} category`} value={c.category} onChange={(e) => set(i, { category: e.target.value })}>{CATEGORIES.map((k) => <option key={k} value={k}>{label(k)}</option>)}</Select>
          <Input aria-label={`Criterion ${i + 1} marks`} type="number" step="0.25" min="0.25" value={c.max_marks} onChange={(e) => set(i, { max_marks: Number(e.target.value) })} />
          <Button type="button" variant="ghost" size="icon" aria-label={`Remove criterion ${i + 1}`} onClick={() => onChange(value.filter((_, j) => j !== i))} disabled={value.length === 1}><Trash2 className="h-4 w-4" /></Button>
          <Textarea aria-label={`Criterion ${i + 1} expected evidence`} className="min-h-16 sm:col-span-4" value={c.expected_evidence} onChange={(e) => set(i, { expected_evidence: e.target.value })} placeholder="What demonstrates this in an answer (any wording)" />
        </fieldset>
      ))}
      <div className="flex items-center justify-between">
        <Button type="button" size="sm" variant="secondary" onClick={() => onChange([...value, { criterion: "", category: "coverage", max_marks: 1, expected_evidence: "" }])}><Plus className="h-3.5 w-3.5" />Add criterion</Button>
        <p className={`text-sm tabular-nums ${Math.abs(total - marks) > 1e-6 ? "text-mark" : "text-success"}`}>Criteria total {total} of {marks}</p>
      </div>
    </div>
  );
}

export const rubricValid = (v: CriterionDraft[], marks: number) =>
  v.length > 0 && v.every((c) => c.criterion.trim().length >= 2 && c.max_marks > 0) && Math.abs(v.reduce((s, c) => s + Number(c.max_marks), 0) - marks) < 1e-6;
