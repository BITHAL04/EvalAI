import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RubricEditor, rubricValid } from "@/components/teacher/rubric-editor";
import { Marks, StatusBadge } from "@/components/ui";
import { parseError } from "@/lib/api";
import { fmtMarks, label, pct } from "@/lib/utils";

describe("formatting", () => {
  it("formats marks without trailing zeros", () => {
    expect(fmtMarks(7.5)).toBe("7.5");
    expect(fmtMarks(8)).toBe("8");
    expect(fmtMarks(null)).toBe("–");
    expect(pct(15, 20)).toBe(75);
    expect(label("pending_teacher_review")).toBe("Pending teacher review");
  });

  it("renders marks against their maximum", () => {
    render(<Marks got={7.25} max={10} />);
    expect(screen.getByText("7.25")).toBeInTheDocument();
    expect(screen.getByText("/10")).toBeInTheDocument();
  });

  it("names statuses in plain language", () => {
    render(<StatusBadge status="evaluated" />);
    expect(screen.getByText("Awaiting teacher")).toBeInTheDocument();
  });
});

describe("rubric editor", () => {
  const rubric = [{ criterion: "Concept", category: "coverage", max_marks: 3, expected_evidence: "" }, { criterion: "Clarity", category: "organization", max_marks: 2, expected_evidence: "" }];

  it("requires criteria to add up to the question's marks", () => {
    expect(rubricValid(rubric, 5)).toBe(true);
    expect(rubricValid(rubric, 6)).toBe(false);
    expect(rubricValid([{ ...rubric[0], criterion: "" }], 3)).toBe(false);
  });

  it("shows the running total and edits criteria", () => {
    const onChange = vi.fn();
    render(<RubricEditor value={rubric} onChange={onChange} marks={6} />);
    expect(screen.getByText("Criteria total 5 of 6")).toHaveClass("text-mark");
    fireEvent.change(screen.getByLabelText("Criterion 1 marks"), { target: { value: "4" } });
    expect(onChange).toHaveBeenCalledWith([{ ...rubric[0], max_marks: 4 }, rubric[1]]);
  });
});

describe("API errors", () => {
  it("surfaces the server's message and field errors", async () => {
    const res = new Response(JSON.stringify({ detail: { code: "validation_error", message: "Invalid input", errors: [{ field: "name", message: "too short" }] } }), { status: 422 });
    const e = await parseError(res);
    expect(e.status).toBe(422);
    expect(e.fields[0].field).toBe("name");
  });

  it("explains rate limiting even without a body", async () => {
    const e = await parseError(new Response("", { status: 429 }));
    expect(e.message).toMatch(/Too many requests/);
  });
});
