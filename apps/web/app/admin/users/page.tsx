"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Badge, Button, Card, ConfirmButton, ErrorState, Field, Input, LoadingBlock, PageHeader, Select, Table, Td } from "@/components/ui";
import { useMe } from "@/hooks/use-me";
import { useApiMutation, useApiQuery } from "@/lib/api";
import type { Page } from "@/types/api";

type U = { id: string; email: string; full_name: string; roll_number: string | null; is_active: boolean; role: string };
const schema = z.object({ email: z.string().email("Enter a valid email"), role: z.enum(["student", "teacher", "admin"]), full_name: z.string() });

export default function People() {
  const me = useMe();
  const [role, setRole] = useState("");
  const [search, setSearch] = useState("");
  const users = useApiQuery<Page<U>>(["users", role, search], `/users?limit=200${role ? `&role=${role}` : ""}${search ? `&q=${encodeURIComponent(search)}` : ""}`);
  const invites = useApiQuery<{ items: { id: string; email: string; role: string; full_name: string }[] }>(["invitations"], "/invitations");
  const f = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { email: "", role: "student", full_name: "" } });
  const invite = useApiMutation<{ status: string }>({ invalidate: [["invitations"], ["users"]], onSuccess: (r) => { f.reset({ email: "", role: f.getValues("role"), full_name: "" }); import("sonner").then(({ toast }) => toast.success(r.status === "added" ? "Added to your institution" : "Invitation saved. They join when they sign up with this email.")); } });
  const revoke = useApiMutation({ success: "Invitation revoked", invalidate: [["invitations"]] });
  const toggle = useApiMutation({ success: "Access updated", invalidate: [["users"]] });
  const e = f.formState.errors;
  return (
    <>
      <PageHeader title="People" description="Roles are assigned here and enforced by the server. People join by signing up with an invited email address." />
      <Card className="p-5">
        <h2 className="font-semibold">Invite someone</h2>
        <form className="mt-3 grid gap-3 sm:grid-cols-[1.3fr_1fr_160px_auto] sm:items-end" onSubmit={f.handleSubmit((v) => invite.mutate({ path: "/invitations", json: v }))}>
          <Field label="Email" error={e.email?.message}>{(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!e.email} type="email" {...f.register("email")} />}</Field>
          <Field label="Name">{(id) => <Input id={id} {...f.register("full_name")} />}</Field>
          <Field label="Role">{(id) => <Select id={id} {...f.register("role")}><option value="student">Student</option><option value="teacher">Teacher</option><option value="admin">Administrator</option></Select>}</Field>
          <Button type="submit" loading={invite.isPending}>Send invitation</Button>
        </form>
        {!!invites.data?.items.length && (
          <div className="mt-5"><p className="text-sm font-medium">Pending invitations</p>
            <ul className="mt-2 divide-y divide-line text-sm">{invites.data.items.map((i) => <li key={i.id} className="flex items-center justify-between py-2"><span>{i.full_name || i.email} <span className="text-muted">{i.full_name && i.email} · {i.role}</span></span><Button size="sm" variant="ghost" onClick={() => revoke.mutate({ path: `/invitations/${i.id}`, method: "DELETE" })}>Revoke</Button></li>)}</ul>
          </div>
        )}
      </Card>
      <div className="mb-3 mt-8 flex flex-wrap items-center gap-3">
        <h2 className="mr-auto font-semibold">Members</h2>
        <Input aria-label="Search people" placeholder="Search name or email" value={search} onChange={(x) => setSearch(x.target.value)} className="w-64" />
        <Select aria-label="Filter by role" value={role} onChange={(x) => setRole(x.target.value)} className="w-40"><option value="">All roles</option><option value="student">Students</option><option value="teacher">Teachers</option><option value="admin">Administrators</option></Select>
      </div>
      {users.isLoading ? <LoadingBlock /> : users.error ? <ErrorState error={users.error} /> : (
        <Table head={["Name", "Email", "Role", "Status", ""]}>
          {users.data!.items.map((u) => (
            <tr key={u.id}>
              <Td className="font-medium">{u.full_name || "–"}{u.roll_number && <span className="block text-xs font-normal text-muted">{u.roll_number}</span>}</Td>
              <Td>{u.email}</Td><Td className="capitalize">{u.role}</Td>
              <Td>{u.is_active ? <Badge tone="success">Active</Badge> : <Badge>Deactivated</Badge>}</Td>
              <Td className="text-right">{u.id !== me.data?.id && <ConfirmButton title={`Remove ${u.full_name || u.email}'s access?`} body="They can no longer sign in to this institution. Their records are kept." confirmLabel="Remove access" variant="ghost" onConfirm={() => toggle.mutateAsync({ path: `/users/${u.id}/membership`, method: "PUT", json: { is_active: false } })}>Remove access</ConfirmButton>}</Td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
