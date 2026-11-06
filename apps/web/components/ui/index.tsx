"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, Inbox, Loader2, X } from "lucide-react";
import { forwardRef, useId, useState, type ComponentProps, type ReactNode } from "react";
import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-control)] text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-primary text-white hover:bg-primary-hover",
        secondary: "border border-line bg-paper text-ink hover:bg-canvas",
        ghost: "text-muted hover:bg-canvas hover:text-ink",
        danger: "bg-mark text-white hover:bg-[#a11f16]",
        link: "text-primary underline-offset-4 hover:underline px-0",
      },
      size: { sm: "h-8 px-3", md: "h-10 px-4", lg: "h-12 px-6 text-base", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = ComponentProps<"button"> & VariantProps<typeof button> & { asChild?: boolean; loading?: boolean };
export function Button({ className, variant, size, asChild, loading, children, disabled, ...p }: ButtonProps) {
  const C = asChild ? Slot : "button";
  return (
    <C className={cn(button({ variant, size }), className)} disabled={disabled || loading} {...p}>
      {asChild ? children : <>{loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}{children}</>}
    </C>
  );
}

const control = "w-full rounded-[var(--radius-control)] border border-line bg-paper px-3 text-sm text-ink placeholder:text-muted/70 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:bg-canvas aria-[invalid=true]:border-mark";
export const Input = forwardRef<HTMLInputElement, ComponentProps<"input">>(({ className, ...p }, ref) => <input ref={ref} className={cn(control, "h-10", className)} {...p} />);
Input.displayName = "Input";
export const Textarea = forwardRef<HTMLTextAreaElement, ComponentProps<"textarea">>(({ className, ...p }, ref) => <textarea ref={ref} className={cn(control, "min-h-24 py-2 leading-relaxed", className)} {...p} />);
Textarea.displayName = "Textarea";
export const Select = forwardRef<HTMLSelectElement, ComponentProps<"select">>(({ className, ...p }, ref) => <select ref={ref} className={cn(control, "h-10 pr-8", className)} {...p} />);
Select.displayName = "Select";

export function Field({ label, error, hint, children, className }: { label: string; error?: string; hint?: string; children: (id: string, describedBy?: string) => ReactNode; className?: string }) {
  const id = useId();
  const msg = `${id}-msg`;
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={id} className="block text-sm font-medium">{label}</label>
      {children(id, error || hint ? msg : undefined)}
      {error ? <p id={msg} className="text-xs text-mark">{error}</p> : hint ? <p id={msg} className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

export function Card({ className, ...p }: ComponentProps<"div">) {
  return <div className={cn("rounded-[var(--radius-card)] border border-line bg-paper", className)} {...p} />;
}

const tones = {
  neutral: "bg-canvas text-muted border-line",
  primary: "bg-primary-soft text-primary border-primary/15",
  success: "bg-success-soft text-success border-success/15",
  warning: "bg-warning-soft text-warning border-warning/20",
  mark: "bg-mark-soft text-mark border-mark/15",
};
export type Tone = keyof typeof tones;
export function Badge({ tone = "neutral", className, ...p }: ComponentProps<"span"> & { tone?: Tone }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", tones[tone], className)} {...p} />;
}

const STATUS: Record<string, [string, Tone]> = {
  uploaded: ["Uploaded", "neutral"], processing: ["Processing", "primary"], indexed: ["Indexed", "success"], failed: ["Failed", "mark"],
  queued: ["Queued", "neutral"], completed: ["Completed", "success"], requires_review: ["Requires review", "warning"],
  draft: ["Draft", "neutral"], generating: ["Generating", "primary"], review: ["In review", "warning"], published: ["Published", "success"], closed: ["Closed", "neutral"], results_published: ["Results out", "primary"],
  awaiting_upload: ["Awaiting upload", "neutral"], submitted: ["Submitted", "primary"], extracting: ["Reading pages", "primary"], extracted: ["Pages read", "primary"],
  evaluating: ["Evaluating", "primary"], evaluated: ["Awaiting teacher", "warning"], approved: ["Approved", "success"], superseded: ["Replaced", "neutral"],
  provisional: ["Provisional", "warning"], needs_review: ["Needs review", "mark"], teacher_reviewed: ["Teacher reviewed", "primary"],
  under_ai_review: ["Under AI review", "primary"], pending_teacher_review: ["Pending teacher review", "warning"], accepted: ["Accepted", "success"],
  partially_accepted: ["Partially accepted", "success"], rejected: ["Rejected", "neutral"], resolved: ["Resolved", "success"],
  Strong: ["Strong", "success"], Adequate: ["Adequate", "primary"], "Needs Improvement": ["Needs improvement", "mark"],
};
export function StatusBadge({ status }: { status: string }) {
  const [text, tone] = STATUS[status] ?? [status, "neutral" as Tone];
  return <Badge tone={tone}>{text}</Badge>;
}

export function SampleBadge() {
  return <Badge tone="neutral" title="Seeded demonstration record. Not produced by AI evaluation.">Sample data</Badge>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-line/60", className)} />;
}

export function LoadingBlock({ rows = 3 }: { rows?: number }) {
  return <div className="space-y-3" aria-busy="true" aria-label="Loading">{Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>;
}

export function EmptyState({ title, body, action, icon }: { title: string; body?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-[var(--radius-card)] border border-dashed border-line bg-paper px-6 py-12 text-center">
      <div className="mb-3 text-muted">{icon ?? <Inbox className="h-6 w-6" aria-hidden />}</div>
      <p className="font-medium">{title}</p>
      {body && <p className="mt-1 max-w-md text-sm text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: { message: string } | null; retry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-[var(--radius-card)] border border-mark/20 bg-mark-soft p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-mark" aria-hidden />
      <div className="flex-1"><p className="font-medium text-mark">{error?.message ?? "Something went wrong."}</p></div>
      {retry && <Button size="sm" variant="secondary" onClick={retry}>Try again</Button>}
    </div>
  );
}

export function PageHeader({ title, description, actions, back }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; back?: ReactNode }) {
  return (
    <div className="mb-6">
      {back && <div className="mb-2 text-sm">{back}</div>}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold">{title}</h1>
          {description && <div className="mt-1 max-w-2xl text-sm text-muted">{description}</div>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <Card className="p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </Card>
  );
}

export function Progress({ value, label }: { value: number; label: string }) {
  return (
    <div role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} className="h-2 w-full overflow-hidden rounded-full bg-line">
      <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${value}%` }} />
    </div>
  );
}

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;
export function DialogContent({ title, description, children, wide }: { title: string; description?: string; children: ReactNode; wide?: boolean }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-[1px]" />
      <DialogPrimitive.Content className={cn("fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-[var(--radius-card)] bg-paper p-6 shadow-xl", wide ? "max-w-3xl" : "max-w-lg")}>
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <DialogPrimitive.Title className="text-lg font-semibold">{title}</DialogPrimitive.Title>
            {description ? <DialogPrimitive.Description className="mt-1 text-sm text-muted">{description}</DialogPrimitive.Description> : <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>}
          </div>
          <DialogPrimitive.Close className="rounded p-1 text-muted hover:bg-canvas" aria-label="Close"><X className="h-4 w-4" /></DialogPrimitive.Close>
        </div>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

/** Destructive and irreversible actions always go through this. */
export function ConfirmButton({ title, body, confirmLabel, onConfirm, children, variant = "secondary", size = "sm", danger = true, disabled }: {
  title: string; body: string; confirmLabel: string; onConfirm: () => Promise<unknown> | void; children: ReactNode; variant?: ButtonProps["variant"]; size?: ButtonProps["size"]; danger?: boolean; disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant={variant} size={size} disabled={disabled}>{children}</Button></DialogTrigger>
      <DialogContent title={title} description={body}>
        <div className="flex justify-end gap-2">
          <DialogClose asChild><Button variant="secondary">Cancel</Button></DialogClose>
          <Button variant={danger ? "danger" : "primary"} loading={busy} onClick={async () => { setBusy(true); try { await onConfirm(); setOpen(false); } catch { /* toast shown by mutation */ } finally { setBusy(false); } }}>{confirmLabel}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export const Tabs = TabsPrimitive.Root;
export function TabsList({ className, ...p }: ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("mb-4 flex gap-1 border-b border-line", className)} {...p} />;
}
export function TabsTrigger({ className, ...p }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return <TabsPrimitive.Trigger className={cn("-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-muted data-[state=active]:border-primary data-[state=active]:font-medium data-[state=active]:text-ink", className)} {...p} />;
}
export const TabsContent = TabsPrimitive.Content;

export function Table({ head, children, className }: { head: ReactNode[]; children: ReactNode; className?: string }) {
  return (
    <div className={cn("overflow-x-auto rounded-[var(--radius-card)] border border-line bg-paper", className)}>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line bg-canvas/60 text-muted"><tr>{head.map((h, i) => <th key={i} className="px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}
export function Td({ className, ...p }: ComponentProps<"td">) {
  return <td className={cn("px-4 py-3 align-top", className)} {...p} />;
}

/** Marks rendered in examiner's red: used only for scores. */
export function Marks({ got, max, className }: { got: number | null | undefined; max: number; className?: string }) {
  const f = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0$/, ""));
  return <span className={cn("font-semibold tabular-nums text-mark", className)}>{got === null || got === undefined ? "–" : f(got)}<span className="font-normal text-muted">/{f(max)}</span></span>;
}
