import { Check, Minus } from "lucide-react";
import Link from "next/link";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui";
import { HeroSheet } from "./hero-sheet";

const lifecycle = [
  ["Upload course material", "Textbooks, notes and past papers become a searchable knowledge base for your subject."],
  ["Generate the paper", "Set marks, difficulty and topics. Each question cites the pages it was written from."],
  ["Approve key and rubric", "Edit questions, model answers and criteria. Nothing reaches students until you publish."],
  ["Students write on paper", "They download the paper, answer in their notebooks and upload a scan or photos as one PDF."],
  ["Read the handwriting", "Every page is transcribed and matched to its question. Unreadable words are marked, never guessed."],
  ["Mark against the rubric", "Criterion by criterion, with evidence quoted from the answer and a confidence signal."],
  ["Teacher signs off", "Flagged answers wait for you. Marks stay provisional until you approve them."],
  ["Results and disputes", "Students see feedback by question and topic, and can challenge a mark with their reasoning."],
];

const comparison: [string, boolean, boolean, boolean][] = [
  ["Marks meaning, not keywords", true, false, false],
  ["Reads handwritten answer booklets", true, false, true],
  ["Criterion-wise marks with quoted evidence", true, false, false],
  ["Teacher approval before any result is shown", true, true, true],
  ["Structured challenge and re-evaluation workflow", true, false, false],
  ["Topic-level feedback for every student", true, false, false],
];

export default function Landing() {
  return (
    <div className="bg-paper">
      <header className="sticky top-0 z-30 border-b border-line/70 bg-paper/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <Logo />
          <nav aria-label="Sections" className="hidden gap-7 text-sm text-muted md:flex">
            <a href="#how-it-works" className="hover:text-ink">How it works</a>
            <a href="#evaluation" className="hover:text-ink">Evaluation</a>
            <a href="#challenges" className="hover:text-ink">Challenges</a>
            <a href="#compare" className="hover:text-ink">Compare</a>
          </nav>
          <div className="flex gap-2">
            <Button asChild variant="ghost" size="sm"><Link href="/sign-in">Sign in</Link></Button>
            <Button asChild size="sm"><Link href="/sign-up">Get Started</Link></Button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-16 lg:grid-cols-[1.05fr_1fr] lg:pt-24">
        <div>
          <h1 className="text-[2.6rem] font-semibold leading-[1.05] sm:text-6xl">Examinations, Reimagined with AI.</h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted">
            From intelligent question generation to handwritten answer evaluation, EvalAI transforms the entire examination lifecycle into an intelligent assessment experience.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg"><Link href="/sign-up">Get Started</Link></Button>
            <Button asChild size="lg" variant="secondary"><a href="#how-it-works">Explore Platform</a></Button>
          </div>
          <p className="mt-6 text-sm text-muted">Understand. Evaluate. Improve.</p>
        </div>
        <HeroSheet />
      </section>

      <section className="border-y border-line bg-canvas">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 md:grid-cols-3">
          <div className="md:col-span-1"><h2 className="text-2xl font-semibold">Built for how exams are actually written</h2></div>
          <p className="text-muted md:col-span-2 md:text-lg md:leading-relaxed">
            Students still think best with a pen. EvalAI keeps the notebook and removes the bottleneck after it: reading hundreds of pages, applying one rubric
            consistently, and explaining every mark. A correct explanation in the student&apos;s own words earns the same credit as the textbook phrasing.
          </p>
        </div>
      </section>

      <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-20">
        <h2 className="text-3xl font-semibold">How it works</h2>
        <p className="mt-2 max-w-2xl text-muted">One workflow from course material to resolved disputes. Each step is recorded.</p>
        <ol className="mt-10 grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-4">
          {lifecycle.map(([t, d], i) => (
            <li key={t} className="border-t border-line pt-4">
              <span className="text-sm font-semibold tabular-nums text-primary">{i + 1}</span>
              <h3 className="mt-1 font-semibold">{t}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{d}</p>
            </li>
          ))}
        </ol>
      </section>

      <section id="evaluation" className="scroll-mt-20 bg-ink text-white">
        <div className="mx-auto grid max-w-6xl gap-12 px-4 py-20 lg:grid-cols-2">
          <div>
            <h2 className="text-3xl font-semibold">Twelve checks behind every mark</h2>
            <p className="mt-3 text-white/70">Marking is a sequence of separate judgements, not one guess. The final score is added up from criteria, never invented.</p>
            <ul className="mt-8 space-y-4 text-sm">
              {[
                ["Understands the question first", "Every student is marked against the same reading of what the question asks."],
                ["Separates missing from wrong", "Leaving something out and stating something false are treated differently, with the quote shown."],
                ["Looks at the page, not just the text", "Diagrams and equations are checked against the original scan."],
                ["Knows when it is unsure", "Low recognition or weak evidence sends the answer to you instead of guessing."],
              ].map(([t, d]) => (
                <li key={t} className="flex gap-3"><Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" aria-hidden /><span><span className="font-medium">{t}.</span> <span className="text-white/70">{d}</span></span></li>
              ))}
            </ul>
          </div>
          <figure className="rounded-[var(--radius-card)] bg-white/5 p-6 ring-1 ring-white/10" aria-label="Example criterion breakdown">
            <figcaption className="text-sm text-white/60">Q1 · Explain the working of a CNN · 10 marks</figcaption>
            {[["Conceptual explanation", 3, 2.5, "Convolution and feature maps explained correctly."], ["Coverage of layers", 3, 2, "Pooling covered; output layer interpretation missing."], ["Labelled diagram", 2, 2, "Diagram matches the description."], ["Clarity", 2, 1, "Steps out of order in the second paragraph."]].map(([c, m, g, r]) => (
              <div key={c as string} className="mt-4 border-t border-white/10 pt-4">
                <div className="flex justify-between text-sm"><span>{c}</span><span className="font-semibold tabular-nums text-[#ff8a80]">{g}<span className="font-normal text-white/50">/{m}</span></span></div>
                <p className="mt-1 text-sm text-white/60">{r}</p>
              </div>
            ))}
            <div className="mt-5 flex justify-between border-t border-white/20 pt-4 font-semibold"><span>Provisional total</span><span className="text-[#ff8a80]">7.5<span className="font-normal text-white/50">/10</span></span></div>
            <p className="mt-2 text-xs text-white/50">Illustration. Real marks appear only after teacher approval.</p>
          </figure>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-12 px-4 py-20 lg:grid-cols-2">
        <div>
          <h2 className="text-3xl font-semibold">Feedback a student can act on</h2>
          <p className="mt-3 text-muted">
            Every result breaks down by question and by topic. Recommendations come from the marks themselves, and say whether a gap is in understanding
            the concept or in explaining it.
          </p>
        </div>
        <figure aria-label="Illustration of topic mastery" className="rounded-[var(--radius-card)] border border-line p-6">
          {[["Neural networks", 82, "bg-success"], ["Optimisation", 68, "bg-primary"], ["CNN architecture", 55, "bg-warning"], ["Regularisation", 41, "bg-mark"]].map(([t, v, c]) => (
            <div key={t as string} className="mb-4 last:mb-0">
              <div className="mb-1 flex justify-between text-sm"><span>{t}</span><span className="tabular-nums text-muted">{v}%</span></div>
              <div className="h-2 rounded-full bg-canvas"><div className={`h-2 rounded-full ${c}`} style={{ width: `${v}%` }} /></div>
            </div>
          ))}
          <figcaption className="mt-4 text-xs text-muted">Illustration. In the product, every chart is drawn from recorded marks.</figcaption>
        </figure>
      </section>

      <section id="challenges" className="scroll-mt-20 border-y border-line bg-canvas">
        <div className="mx-auto max-w-6xl px-4 py-20">
          <h2 className="text-3xl font-semibold">Disagree with a mark? Make the case.</h2>
          <p className="mt-3 max-w-2xl text-muted">Students pick the criterion they dispute and explain why. EvalAI checks the argument against the key, the rubric, their answer and the course material, then hands a recommendation to the teacher.</p>
          <ol className="mt-10 grid gap-6 md:grid-cols-4">
            {[["Student challenges", "A specific criterion, with reasoning and evidence."], ["AI reviews the argument", "Is the alternative valid? Is the key incomplete?"], ["Teacher decides", "Accept, partially accept or reject, with a reason."], ["History is kept", "Original and revised marks, rubric versions and decisions."]].map(([t, d], i) => (
              <li key={t} className="rounded-[var(--radius-card)] bg-paper p-5 ring-1 ring-line">
                <span className="text-sm font-semibold text-primary">{i + 1}</span>
                <h3 className="mt-1 font-semibold">{t}</h3>
                <p className="mt-1 text-sm text-muted">{d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="compare" className="mx-auto max-w-4xl scroll-mt-20 px-4 py-20">
        <h2 className="text-3xl font-semibold">How EvalAI compares</h2>
        <div className="mt-8 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-left text-muted"><th className="py-3 font-medium">Capability</th><th className="py-3 font-medium text-ink">EvalAI</th><th className="py-3 font-medium">Keyword matching</th><th className="py-3 font-medium">Manual marking</th></tr></thead>
            <tbody>
              {comparison.map(([c, ...v]) => (
                <tr key={c} className="border-b border-line">
                  <td className="py-3 pr-4">{c}</td>
                  {v.map((x, i) => <td key={i} className="py-3">{x ? <Check className="h-4 w-4 text-success" aria-label="Yes" /> : <Minus className="h-4 w-4 text-muted" aria-label="No" />}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-20">
        <div className="rounded-[var(--radius-card)] bg-primary px-8 py-14 text-white md:flex md:items-center md:justify-between">
          <div>
            <h2 className="text-3xl font-semibold">Run your next exam on EvalAI</h2>
            <p className="mt-2 text-white/75">Upload your notes, generate a paper and review the first answer sheets yourself.</p>
          </div>
          <Button asChild size="lg" variant="secondary" className="mt-6 border-0 md:mt-0"><Link href="/sign-up">Get Started</Link></Button>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-8 text-sm text-muted">
          <Logo />
          <p>Understand. Evaluate. Improve.</p>
          <div className="flex gap-5"><Link href="/sign-in" className="hover:text-ink">Sign in</Link><a href="#how-it-works" className="hover:text-ink">How it works</a></div>
        </div>
      </footer>
    </div>
  );
}
