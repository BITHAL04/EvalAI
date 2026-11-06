"use client";

import { useState } from "react";
import { useApiMutation, useApiQuery } from "@/lib/api";
import { Button, Card, Field, Input } from "./ui";

export function Courses() {
  const q = useApiQuery<{ items: { id: string; name: string; code: string }[] }>(["courses"], "/courses");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const add = useApiMutation({ success: "Course created", invalidate: [["courses"]], onSuccess: () => { setName(""); setCode(""); } });
  return (
    <Card className="mt-8 p-5">
      <h2 className="font-semibold">Courses</h2>
      <p className="mt-1 text-sm text-muted">Programmes that group subjects, e.g. B.Tech Computer Science.</p>
      {q.data?.items.length ? <ul className="mt-3 divide-y divide-line text-sm">{q.data.items.map((c) => <li key={c.id} className="flex justify-between py-2"><span>{c.name}</span><span className="text-muted">{c.code}</span></li>)}</ul> : <p className="mt-3 text-sm text-muted">No courses yet.</p>}
      <form className="mt-4 grid gap-3 sm:grid-cols-[1fr_160px_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); add.mutate({ path: "/courses", json: { name, code } }); }}>
        <Field label="Course name">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />}</Field>
        <Field label="Code">{(id) => <Input id={id} value={code} onChange={(e) => setCode(e.target.value)} required minLength={2} />}</Field>
        <Button type="submit" loading={add.isPending}>Add course</Button>
      </form>
    </Card>
  );
}
