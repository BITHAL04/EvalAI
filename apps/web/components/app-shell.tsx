"use client";

import { Bell, BookOpen, ClipboardCheck, FileStack, FileText, Gavel, GraduationCap, LayoutDashboard, LineChart, Library, LogOut, Menu, ScrollText, Server, Users, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useMe } from "@/hooks/use-me";
import { useApiMutation, useApiQuery } from "@/lib/api";
import { useSession } from "@/lib/auth";
import { AUTH_MODE } from "@/lib/config";
import { cn, fmtDate } from "@/lib/utils";
import type { Notification, Role } from "@/types/api";
import { AuthNotConfigured } from "./config-error";
import { Logo } from "./logo";
import { Button, Dialog, DialogContent, DialogTrigger, ErrorState, LoadingBlock } from "./ui";

const NAV: Record<Role, { href: string; label: string; icon: typeof LayoutDashboard }[]> = {
  teacher: [
    { href: "/teacher", label: "Overview", icon: LayoutDashboard },
    { href: "/teacher/subjects", label: "Subjects", icon: BookOpen },
    { href: "/teacher/documents", label: "Documents", icon: Library },
    { href: "/teacher/questions", label: "Question bank", icon: FileStack },
    { href: "/teacher/exams", label: "Examinations", icon: FileText },
    { href: "/teacher/challenges", label: "Challenges", icon: Gavel },
    { href: "/teacher/analytics", label: "Analytics", icon: LineChart },
  ],
  student: [
    { href: "/student", label: "Overview", icon: LayoutDashboard },
    { href: "/student/exams", label: "Examinations", icon: FileText },
    { href: "/student/results", label: "Results", icon: ClipboardCheck },
    { href: "/student/challenges", label: "Challenges", icon: Gavel },
  ],
  admin: [
    { href: "/admin", label: "Overview", icon: LayoutDashboard },
    { href: "/admin/users", label: "People", icon: Users },
    { href: "/admin/subjects", label: "Subjects", icon: GraduationCap },
    { href: "/admin/processing", label: "AI processing", icon: Server },
    { href: "/admin/audit", label: "Audit log", icon: ScrollText },
  ],
};

function Notifications() {
  const q = useApiQuery<{ items: Notification[]; unread: number }>(["notifications"], "/notifications?limit=20", { refetchInterval: 30_000 });
  const readAll = useApiMutation({ invalidate: [["notifications"]] });
  const router = useRouter();
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o && q.data?.unread) readAll.mutate({ path: "/notifications/read-all" }); }}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Notifications${q.data?.unread ? `, ${q.data.unread} unread` : ""}`} className="relative">
          <Bell className="h-4 w-4" />
          {!!q.data?.unread && <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-mark" />}
        </Button>
      </DialogTrigger>
      <DialogContent title="Notifications">
        {q.isLoading ? <LoadingBlock /> : !q.data?.items.length ? <p className="text-sm text-muted">Nothing yet. Updates about documents, papers, evaluations and challenges appear here.</p> : (
          <ul className="divide-y divide-line">
            {q.data.items.map((n) => (
              <li key={n.id}>
                <button className="w-full py-3 text-left hover:bg-canvas/60" onClick={() => { setOpen(false); if (n.link) router.push(n.link); }}>
                  <p className={cn("text-sm", !n.read && "font-semibold")}>{n.title}</p>
                  {n.body && <p className="text-sm text-muted">{n.body}</p>}
                  <p className="mt-0.5 text-xs text-muted">{fmtDate(n.created_at)}</p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function AppShell({ role, children }: { role: Role; children: ReactNode }) {
  const { ready, signedIn, signOut } = useSession();
  const me = useMe();
  const router = useRouter();
  const path = usePathname();
  // The mobile menu belongs to the page it was opened on, so navigating closes it.
  const [menuPath, setMenuPath] = useState<string | null>(null);
  const menu = menuPath === path;
  const setMenu = (open: boolean) => setMenuPath(open ? path : null);

  useEffect(() => { if (ready && !signedIn) router.replace("/sign-in"); }, [ready, signedIn, router]);
  useEffect(() => { if (me.error?.code === "not_synced" || me.error?.code === "no_membership") router.replace("/dashboard"); }, [me.error, router]);
  useEffect(() => { if (me.data?.role && me.data.role !== role) router.replace(`/${me.data.role}`); }, [me.data, role, router]);

  if (AUTH_MODE === "none") return <AuthNotConfigured />;
  if (!ready || me.isLoading || !me.data || me.data.role !== role) {
    return <div className="mx-auto max-w-3xl p-8">{me.error && !["not_synced", "no_membership"].includes(me.error.code) ? <ErrorState error={me.error} retry={() => me.refetch()} /> : <LoadingBlock />}</div>;
  }
  const items = NAV[role];
  const active = (href: string) => (href === `/${role}` ? path === href : path.startsWith(href));
  const nav = (
    <nav aria-label="Main" className="space-y-0.5">
      {items.map(({ href, label, icon: Icon }) => (
        <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
          className={cn("flex items-center gap-2.5 rounded-[var(--radius-control)] px-3 py-2 text-sm", active(href) ? "bg-primary-soft font-medium text-primary" : "text-muted hover:bg-canvas hover:text-ink")}>
          <Icon className="h-4 w-4" aria-hidden />{label}
        </Link>
      ))}
    </nav>
  );
  const institution = me.data.memberships[0]?.institution;
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-line bg-paper p-4 lg:flex">
        <div className="px-2 pb-6 pt-1"><Logo href={`/${role}`} /></div>
        {nav}
        <div className="mt-auto border-t border-line px-2 pt-4">
          <p className="truncate text-sm font-medium">{me.data.full_name || me.data.email}</p>
          <p className="truncate text-xs text-muted">{institution} · {role}</p>
          <button onClick={() => signOut()} className="mt-3 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink"><LogOut className="h-3.5 w-3.5" aria-hidden />Sign out</button>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-paper/90 px-4 backdrop-blur lg:justify-end lg:px-8">
          <div className="flex items-center gap-2 lg:hidden">
            <Button variant="ghost" size="icon" aria-label="Open menu" onClick={() => setMenu(true)}><Menu className="h-5 w-5" /></Button>
            <Logo href={`/${role}`} />
          </div>
          <Notifications />
        </header>
        {menu && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
            <div className="absolute inset-0 bg-ink/30" onClick={() => setMenu(false)} />
            <div className="absolute inset-y-0 left-0 w-72 bg-paper p-4">
              <div className="mb-6 flex items-center justify-between"><Logo href={`/${role}`} /><Button variant="ghost" size="icon" aria-label="Close menu" onClick={() => setMenu(false)}><X className="h-5 w-5" /></Button></div>
              {nav}
              <button onClick={() => signOut()} className="mt-6 inline-flex items-center gap-1.5 px-3 text-sm text-muted"><LogOut className="h-3.5 w-3.5" aria-hidden />Sign out</button>
            </div>
          </div>
        )}
        <main className="mx-auto max-w-6xl px-4 py-8 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
