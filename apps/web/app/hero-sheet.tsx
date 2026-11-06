"use client";

import { motion, useReducedMotion } from "framer-motion";

const lines = [
  "Q1. A CNN slides small filters over the",
  "image, so each filter makes a feature map",
  "that lights up where its pattern appears.",
  "Pooling then shrinks the maps, keeping the",
  "strongest signal, and the dense layer at the",
  "end turns them into class scores.",
];

const marks = [
  { line: 1, text: "convolution ✓", note: "+2.5" },
  { line: 3, text: "pooling ✓", note: "+2" },
  { line: 5, text: "why? output not explained", note: "−1" },
];

/** The one orchestrated moment on the page: the examiner's marks arrive on a handwritten answer. */
export function HeroSheet() {
  const reduce = useReducedMotion();
  return (
    <figure className="relative" aria-label="A handwritten answer with rubric marks in the margin">
      <div className="ruled-paper relative overflow-hidden rounded-[var(--radius-card)] border border-line pb-8 pl-14 pr-6 pt-[34px] shadow-[0_24px_60px_-28px_rgba(20,26,46,.35)]">
        <div className="absolute inset-y-0 left-10 w-px bg-mark/40" aria-hidden />
        {lines.map((l, i) => (
          <p key={i} className="font-hand text-[22px] leading-[34px] text-[#25307a] sm:text-[25px]">{l}</p>
        ))}
        <motion.div initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.6, duration: .4 }}
          className="mt-4 flex items-baseline justify-end gap-2 font-hand text-[30px] text-mark">
          <span className="border-b-2 border-mark/70 px-1">7.5 / 10</span>
        </motion.div>
      </div>
      <div className="pointer-events-none absolute inset-0" aria-hidden>
        {marks.map((m, i) => (
          <motion.div key={m.text} initial={reduce ? false : { opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 + i * 0.35, duration: .35 }}
            className="absolute -right-2 flex items-center gap-2 sm:-right-6" style={{ top: 34 + m.line * 34 - 2 }}>
            <span className="rounded-md bg-paper px-2 py-0.5 font-hand text-[19px] text-mark shadow-sm ring-1 ring-mark/20">{m.note} {m.text}</span>
          </motion.div>
        ))}
      </div>
      <figcaption className="mt-3 text-xs text-muted">Illustration of a marked answer. Marks are provisional until a teacher approves them.</figcaption>
    </figure>
  );
}
