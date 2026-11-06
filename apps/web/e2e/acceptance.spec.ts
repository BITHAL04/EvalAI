import { expect, test } from "@playwright/test";
import { fixture, makeFixtures, nav, person, signIn, sql, type Person } from "./helpers";

/**
 * The primary acceptance flow from the product specification, driven entirely through the UI.
 * Identity and the model are the local HTTP test doubles; everything else is the real stack.
 */
test.describe.configure({ mode: "serial" });

let teacher: Person, student: Person, admin: Person;
const EXAM = "Machine Learning — Unit Test 1";

test.beforeAll(() => {
  makeFixtures();
  const inst = sql("insert into institutions (id, name, slug, settings, is_active, is_demo) values (gen_random_uuid(), 'E2E Institute', 'e2e-institute', '{}', true, false) on conflict (slug) do update set name = excluded.name returning id");
  teacher = person("Tara Teacher", "teacher", inst);
  student = person("Sam Student", "student", inst);
  admin = person("Ada Admin", "admin", inst);
});

test("landing page", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Examinations, Reimagined with AI.");
  await page.getByRole("link", { name: "Explore Platform" }).click();
  await expect(page.getByRole("heading", { name: "How it works" })).toBeInViewport();
});

test("teacher: subject, document, generated paper, publish", async ({ page }) => {
  await signIn(page, student); // student account must exist before it can be enrolled
  await expect(page).toHaveURL(/\/student$/);
  await signIn(page, teacher);
  await expect(page).toHaveURL(/\/teacher$/);

  await nav(page, "Subjects");
  await page.getByRole("button", { name: "New subject" }).click();
  await page.getByLabel("Name").fill("Machine Learning");
  await page.getByLabel("Code").fill("ML301");
  await page.getByRole("button", { name: "Create subject" }).click();
  await expect(page.getByRole("heading", { name: "Machine Learning" })).toBeVisible();
  await page.getByRole("button", { name: "Students" }).click();
  await page.getByLabel(/Sam Student/).check();
  await page.getByRole("button", { name: /Enrol 1 selected/ }).click();
  await expect(page.getByText("Enrolled (1)")).toBeVisible();
  await page.keyboard.press("Escape");

  await nav(page, "Documents");
  await page.getByLabel("File").setInputFiles(fixture("ml-notes.pdf"));
  await page.getByLabel("Title").fill("ML lecture notes");
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText("Indexed", { exact: true })).toBeVisible({ timeout: 60_000 });

  await nav(page, "Examinations");
  await page.getByRole("link", { name: "Create examination" }).first().click();
  await page.getByLabel("Title").fill(EXAM);
  await page.getByLabel("Subject").selectOption({ label: "Machine Learning" });
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Chapter 1 Neural Networks" }).click();
  await page.getByRole("button", { name: "Chapter 2 Convolutional Neural Networks" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Total marks").fill("20");
  await page.getByLabel("Row 1 number of questions").fill("1");
  await page.getByLabel("Row 2 number of questions").fill("2");
  await expect(page.getByText("20 of 20 marks allocated")).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Generate paper" }).click();

  await expect(page.getByText("In review")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/^Q[123]$/)).toHaveCount(3);
  await page.getByRole("button", { name: "Answer key, rubric and sources" }).first().click();
  await expect(page.getByText("ML lecture notes, pages").first()).toBeVisible();
  await page.getByRole("button", { name: "Approve and publish" }).click();
  await page.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(page.getByText("Published", { exact: true }).first()).toBeVisible();
});

test("student: view paper and submit a handwritten answer sheet", async ({ page }) => {
  await signIn(page, student);
  await nav(page, "Examinations");
  await page.getByRole("link", { name: "Open" }).first().click();
  await expect(page.getByRole("heading", { name: EXAM })).toBeVisible();
  const popup = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Download question paper" }).click();
  expect((await popup).url()).toContain("/api/v1/local-storage/");
  await page.getByLabel("Answer sheet PDF").setInputFiles(fixture("answer-booklet.pdf"));
  await expect(page.getByAltText("Page 2")).toBeVisible();
  await page.getByRole("button", { name: "Submit answer sheet" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Submit answer sheet" }).click();
  await expect(page.getByRole("heading", { name: "Submitted" })).toBeVisible();
  await expect(page.getByText(/Awaiting teacher/)).toBeVisible({ timeout: 120_000 });
});

test("teacher: review provisional marks, approve and publish results", async ({ page }) => {
  await signIn(page, teacher);
  await nav(page, "Examinations");
  await page.getByRole("link", { name: EXAM }).click();
  await page.getByRole("tab", { name: "Submissions" }).click();
  await page.getByRole("link", { name: "Review" }).click();
  await expect(page.getByText("Provisional total")).toBeVisible();
  await expect(page.getByAltText("Answer sheet page 1")).toBeVisible();

  // Every flagged answer must be looked at before approval is possible.
  while (await page.getByRole("button", { name: "Review marks" }).count()) {
    await page.getByRole("button", { name: "Review marks" }).first().click();
    const dialog = page.getByRole("dialog");
    for (const reason of await dialog.getByLabel(/ reason$/).all()) if (!(await reason.inputValue())) await reason.fill("Checked against the page");
    await dialog.getByLabel(/changing or confirming/).fill("Checked against the original page");
    await dialog.getByRole("button", { name: "Save marks" }).click();
    await expect(dialog).toBeHidden();
  }
  await page.getByRole("button", { name: "Approve marks" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve marks" }).click();
  await expect(page.getByText("Approved total")).toBeVisible();

  await page.getByRole("link", { name: EXAM }).click();
  await page.getByRole("button", { name: "Publish results" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Publish results" }).click();
  await expect(page.getByText("1 result published")).toBeVisible();
});

test("student: sees result and challenges a mark", async ({ page }) => {
  await signIn(page, student);
  await nav(page, "Results");
  await page.getByRole("link", { name: EXAM }).click();
  await expect(page.getByText("Question by question")).toBeVisible();
  await page.getByRole("button", { name: /^Q1/ }).click();
  await expect(page.getByText("Marks by criterion")).toBeVisible();
  await page.getByRole("button", { name: "Challenge this mark" }).click();
  await page.getByLabel("Explain why").fill("I explained pooling and the fully connected layer on page 2; please check those lines again.");
  await page.getByRole("button", { name: "Submit challenge" }).click();
  await expect(page.getByText("Challenge submitted")).toBeVisible();
});

test("teacher: resolves the challenge; student sees the new mark", async ({ page }) => {
  await signIn(page, teacher);
  await nav(page, "Challenges");
  await page.getByRole("link", { name: "Sam Student" }).click({ timeout: 60_000 });
  await expect(page.getByText("Partially accept").first()).toBeVisible({ timeout: 60_000 });
  const original = Number(await page.getByLabel(/Revised marks/).inputValue());
  await page.getByLabel("Reason (shown to the student)").fill("The pooling explanation on page 2 deserves credit.");
  await page.getByRole("button", { name: "Record decision" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Record decision" }).click();
  await page.getByRole("button", { name: "Mark as resolved" }).click();
  await expect(page.getByText("Resolved").first()).toBeVisible();

  await signIn(page, student);
  await nav(page, "Challenges");
  await page.getByRole("link", { name: "Q1" }).click();
  await expect(page.getByText("Partially accepted").first()).toBeVisible();
  await expect(page.getByText("The pooling explanation on page 2 deserves credit.")).toBeVisible();
  expect(original).toBeGreaterThan(0);

  await signIn(page, admin);
  await nav(page, "Audit log");
  for (const a of ["challenge.decided", "results.published", "submission.approved", "exam.published"]) await expect(page.getByRole("cell", { name: a, exact: true }).first()).toBeVisible();
});
