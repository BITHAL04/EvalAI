"use client";

import { useState } from "react";
import { Button, Card, ErrorState, Field, Input, LoadingBlock, PageHeader, Stat, StatusBadge } from "@/components/ui";
import { useMe } from "@/hooks/use-me";
import { useApiMutation, useApiQuery } from "@/lib/api";

type O = { institution: string; users: Record<string, number>; examinations: Record<string, number>; subjects: number; submissions: number; results: number;
  evaluation_quality: { evaluations: number; average_confidence: number | null; flagged_for_review: number; changed_by_teachers: number } };

function Institutions() {
  const q = useApiQuery<{ items: { id: string; name: string; slug: string; is_active: boolean }[] }>(["institutions"], "/admin/institutions");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const create = useApiMutation({ success: "Institution created. You are its administrator.", invalidate: [["institutions"], ["me"]], onSuccess: () => { setName(""); setSlug(""); } });
  return (
    <Card className="p-5">
      <h2 className="font-semibold">Institutions</h2>
      <p className="mt-1 text-sm text-muted">Visible to platform administrators. Each institution&apos;s data is isolated from the others.</p>
      <ul className="mt-3 divide-y divide-line text-sm">{q.data?.items.map((i) => <li key={i.id} className="flex justify-between py-2"><span>{i.name}</span><span className="text-muted">{i.slug}</span></li>)}</ul>
      <form className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); create.mutate({ path: "/admin/institutions", json: { name, slug } }); }}>
        <Field label="Name">{(id) => <Input id={id} value={name} onChange={(e) => { setName(e.target.value); setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")); }} required minLength={2} />}</Field>
        <Field label="Short name">{(id) => <Input id={id} value={slug} onChange={(e) => setSlug(e.target.value)} pattern="[a-z0-9-]{2,80}" required />}</Field>
        <Button type="submit" loading={create.isPending}>Create institution</Button>
      </form>
    </Card>
  );
}

export default function AdminHome() {
  const me = useMe();
  const o = useApiQuery<O>(["admin-overview"], "/admin/overview");
  if (o.isLoading) return <LoadingBlock rows={4} />;
  if (o.error) return <ErrorState error={o.error} retry={o.refetch} />;
  const d = o.data!;
  const q = d.evaluation_quality;
  return (
    <>
      <PageHeader title={d.institution} description="People, examinations and the health of AI evaluation in your institution." />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Teachers" value={d.users.teacher ?? 0} /><Stat label="Students" value={d.users.student ?? 0} /><Stat label="Subjects" value={d.subjects} /><Stat label="Answer sheets" value={d.submissions} />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="font-semibold">Examinations</h2>
          {Object.keys(d.examinations).length ? <ul className="mt-3 space-y-2">{Object.entries(d.examinations).map(([k, v]) => <li key={k} className="flex items-center justify-between"><StatusBadge status={k} /><span className="tabular-nums">{v}</span></li>)}</ul> : <p className="mt-3 text-sm text-muted">None yet.</p>}
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">Evaluation quality</h2>
          <p className="mt-1 text-xs text-muted">AI evaluations only; seeded sample records are excluded.</p>
          <dl className="mt-3 grid grid-cols-2 gap-4 text-sm">
            <div><dt className="text-muted">Answers evaluated</dt><dd className="text-xl font-semibold tabular-nums">{q.evaluations}</dd></div>
            <div><dt className="text-muted">Average confidence signal</dt><dd className="text-xl font-semibold tabular-nums">{q.average_confidence !== null ? `${Math.round(q.average_confidence * 100)}%` : "–"}</dd></div>
            <div><dt className="text-muted">Flagged for review</dt><dd className="text-xl font-semibold tabular-nums">{q.flagged_for_review}</dd></div>
            <div><dt className="text-muted">Changed by teachers</dt><dd className="text-xl font-semibold tabular-nums">{q.changed_by_teachers}</dd></div>
          </dl>
        </Card>
        {me.data?.is_platform_admin && <div className="lg:col-span-2"><Institutions /></div>}
      </div>
    </>
  );
}
