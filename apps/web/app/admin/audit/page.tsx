"use client";

import { useState } from "react";
import { Button, ErrorState, Input, LoadingBlock, PageHeader, Table, Td } from "@/components/ui";
import { useApiQuery } from "@/lib/api";
import { fmtDate } from "@/lib/utils";

type A = { total: number; items: { id: string; action: string; entity_type: string; entity_id: string | null; actor: string; before: unknown; after: unknown; created_at: string }[] };
const SIZE = 50;

export default function Audit() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(0);
  const q = useApiQuery<A>(["audit", action, page], `/admin/audit-logs?limit=${SIZE}&offset=${page * SIZE}${action ? `&action=${encodeURIComponent(action)}` : ""}`);
  return (
    <>
      <PageHeader title="Audit log" description="Every significant action, by people, the AI and the system. Entries cannot be edited or deleted."
        actions={<Input aria-label="Filter by action" placeholder="Filter, e.g. challenge" value={action} onChange={(e) => { setAction(e.target.value); setPage(0); }} className="w-64" />} />
      {q.isLoading ? <LoadingBlock /> : q.error ? <ErrorState error={q.error} retry={q.refetch} /> : (
        <>
          <Table head={["When", "Action", "By", "Record", "Change"]}>
            {q.data!.items.map((a) => (
              <tr key={a.id}>
                <Td className="whitespace-nowrap text-muted">{fmtDate(a.created_at)}</Td>
                <Td className="font-medium">{a.action}</Td>
                <Td>{a.actor}</Td>
                <Td className="text-xs text-muted">{a.entity_type}{a.entity_id ? ` ${a.entity_id.slice(0, 8)}` : ""}</Td>
                <Td className="max-w-sm"><code className="block truncate text-xs" title={JSON.stringify({ before: a.before, after: a.after })}>{a.before ? `${JSON.stringify(a.before)} → ` : ""}{a.after ? JSON.stringify(a.after) : ""}</code></Td>
              </tr>
            ))}
          </Table>
          <div className="mt-4 flex items-center justify-between text-sm text-muted">
            <span>{q.data!.total} entries</span>
            <div className="flex gap-2"><Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button><Button size="sm" variant="secondary" disabled={(page + 1) * SIZE >= q.data!.total} onClick={() => setPage(page + 1)}>Next</Button></div>
          </div>
        </>
      )}
    </>
  );
}
