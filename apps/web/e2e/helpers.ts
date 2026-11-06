import { execFileSync } from "node:child_process";
import path from "node:path";
import type { Page } from "@playwright/test";

const ROOT = path.resolve(__dirname, "../../..");
const PY = process.env.PY ?? "python";
const RUN = process.env.E2E_DIR ?? "/tmp/evalai-e2e";
const PG = (process.env.PG ?? "127.0.0.1:54329").split(":");

export const fixture = (name: string) => path.join(RUN, "fixtures", name);

export function makeFixtures() {
  execFileSync(PY, [path.join(ROOT, "scripts/make_fixtures.py"), path.join(RUN, "fixtures")]);
}

export function sql(q: string) {
  return execFileSync("psql", ["-h", PG[0], "-p", PG[1], "-U", "postgres", "-d", "evalai_e2e", "-tAqc", q]).toString().trim().split("\n")[0];
}

export type Person = { sub: string; email: string; name: string; token: string };

export function person(name: string, role: "teacher" | "student" | "admin", institutionId: string): Person {
  const slug = name.toLowerCase().replace(/\W+/g, ".");
  const p = { sub: `e2e_${slug}`, email: `${slug}@e2e.evalai.test`, name };
  sql(`insert into invitations (id, institution_id, email, role, full_name) values (gen_random_uuid(), '${institutionId}', '${p.email}', '${role}', '${name}') on conflict do nothing`);
  const token = execFileSync(PY, [path.join(ROOT, "scripts/dev_stubs/test_identity.py"), "mint", "--key", path.join(RUN, "key.pem"), "--sub", p.sub, "--email", p.email]).toString().trim();
  return { ...p, token };
}

export async function signIn(page: Page, who: Person) {
  await page.goto("/");
  await page.evaluate((t) => localStorage.setItem("evalai_test_token", t), who.token);
  await page.goto("/dashboard");
}

export async function nav(page: Page, name: string) {
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name, exact: true }).click();
}
