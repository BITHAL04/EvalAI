"use client";

import { FileUp, RotateCw, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button, Card, ConfirmButton, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Progress, Select, StatusBadge, Table, Td } from "@/components/ui";
import { useSubjects } from "@/hooks/use-subjects";
import { ApiError, uploadWithProgress, useApi, useApiMutation, useApiQuery } from "@/lib/api";
import { bytes, fmtDate, label } from "@/lib/utils";
import type { Material, Page } from "@/types/api";
import { useQueryClient } from "@tanstack/react-query";

const KINDS = ["textbook", "ebook", "notes", "reference", "course_material", "past_paper", "question_bank"];
const MAX_MB = 50;

function Uploader({ subjectId }: { subjectId: string }) {
  const api = useApi();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("notes");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!file) return;
    setError(null);
    if (!/\.(pdf|txt|docx)$/i.test(file.name)) return setError("Choose a PDF, TXT or DOCX file.");
    if (file.size > MAX_MB * 1024 * 1024) return setError(`Files can be at most ${MAX_MB} MB.`);
    if (title.trim().length < 2) return setError("Give the document a title.");
    try {
      setProgress(0);
      const u = await api<{ upload_url: string; method: string; headers: Record<string, string>; upload_token: string }>("/documents/upload-url", { method: "POST", json: { filename: file.name, size_bytes: file.size, content_type: file.type || "application/octet-stream", subject_id: subjectId } });
      await uploadWithProgress(u.upload_url, u.method, u.headers, file, setProgress);
      await api("/documents", { method: "POST", json: { upload_token: u.upload_token, title: title.trim(), kind } });
      toast.success("Uploaded. Indexing has started.");
      setFile(null); setTitle(""); if (input.current) input.current.value = "";
      qc.invalidateQueries({ queryKey: ["documents"] });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed. Try again.");
    } finally {
      setProgress(null);
    }
  }

  return (
    <Card className="p-5">
      <div className="grid gap-4 md:grid-cols-[1.3fr_1fr_0.8fr_auto] md:items-end">
        <Field label="File" hint={`PDF, TXT or DOCX up to ${MAX_MB} MB`}>{(id, d) => (
          <input id={id} aria-describedby={d} ref={input} type="file" accept=".pdf,.txt,.docx" className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary-soft file:px-3 file:py-2 file:text-primary"
            onChange={(e) => { const f = e.target.files?.[0] ?? null; setFile(f); if (f && !title) setTitle(f.name.replace(/\.\w+$/, "")); }} />
        )}</Field>
        <Field label="Title">{(id) => <Input id={id} value={title} onChange={(e) => setTitle(e.target.value)} />}</Field>
        <Field label="Type">{(id) => <Select id={id} value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map((k) => <option key={k} value={k}>{label(k)}</option>)}</Select>}</Field>
        <Button onClick={submit} disabled={!file} loading={progress !== null}><FileUp className="h-4 w-4" />Upload</Button>
      </div>
      {progress !== null && <div className="mt-4"><Progress value={progress} label="Upload progress" /><p className="mt-1 text-xs text-muted">{progress < 100 ? `Uploading… ${progress}%` : "Checking the file…"}</p></div>}
      {error && <p role="alert" className="mt-3 text-sm text-mark">{error}</p>}
    </Card>
  );
}

export default function Documents() {
  const subjects = useSubjects();
  const [subject, setSubject] = useState("");
  const sid = subject || subjects.data?.items[0]?.id || "";
  const docs = useApiQuery<Page<Material>>(["documents", sid], sid ? `/documents?subject_id=${sid}&limit=100` : null, {
    refetchInterval: (q) => (q.state.data?.items.some((d) => d.status === "uploaded" || d.status === "processing") ? 3000 : false),
  });
  const retry = useApiMutation({ success: "Indexing restarted", invalidate: [["documents", sid]] });
  const del = useApiMutation({ success: "Document deleted", invalidate: [["documents", sid], ["subjects"]] });
  const open = useApi();

  if (subjects.isLoading) return <LoadingBlock />;
  if (subjects.error) return <ErrorState error={subjects.error} />;
  if (!subjects.data!.items.length) return <><PageHeader title="Documents" /><EmptyState title="Create a subject first" body="Documents belong to a subject." /></>;
  return (
    <>
      <PageHeader title="Documents" description="Course material is split into sections and indexed so questions can be generated from it and answers checked against it."
        actions={<Select aria-label="Subject" value={sid} onChange={(e) => setSubject(e.target.value)} className="w-64">{subjects.data!.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>} />
      <Uploader subjectId={sid} />
      <div className="mt-6">
        {docs.isLoading ? <LoadingBlock /> : docs.error ? <ErrorState error={docs.error} retry={docs.refetch} /> : !docs.data!.items.length ? (
          <EmptyState title="No documents in this subject" body="Upload a textbook chapter or lecture notes to start." />
        ) : (
          <Table head={["Document", "Type", "Status", "Sections", "Uploaded", ""]}>
            {docs.data!.items.map((d) => (
              <tr key={d.id}>
                <Td><button className="text-left font-medium hover:text-primary" onClick={async () => { const r = await open<{ download_url: string }>(`/documents/${d.id}`); window.open(r.download_url, "_blank", "noopener"); }}>{d.title}</button><p className="text-xs text-muted">{d.filename} · {bytes(d.size_bytes)}{d.page_count ? ` · ${d.page_count} pages` : ""}</p>
                  {d.error && <p className="mt-1 text-xs text-mark">{d.error}</p>}</Td>
                <Td>{label(d.kind)}</Td>
                <Td><StatusBadge status={d.status} /></Td>
                <Td className="tabular-nums">{d.status === "indexed" ? d.chunk_count : "–"}</Td>
                <Td className="whitespace-nowrap text-muted">{fmtDate(d.created_at)}</Td>
                <Td className="text-right">
                  <div className="flex justify-end gap-1">
                    {d.status === "failed" && <Button size="sm" variant="secondary" loading={retry.isPending} onClick={() => retry.mutate({ path: `/documents/${d.id}/retry` })}><RotateCw className="h-3.5 w-3.5" />Retry</Button>}
                    <ConfirmButton title={`Delete ${d.title}?`} body="It will no longer be used for generating questions or checking answers. Existing papers are not changed." confirmLabel="Delete document" variant="ghost"
                      onConfirm={() => del.mutateAsync({ path: `/documents/${d.id}`, method: "DELETE" })}><Trash2 className="h-3.5 w-3.5" /><span className="sr-only">Delete</span></ConfirmButton>
                  </div>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </div>
    </>
  );
}
