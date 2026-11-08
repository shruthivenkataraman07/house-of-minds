"use client";
/**
 * Typeset maths. Only controlled templates written in this codebase (lib/formulas.ts) are
 * rendered; backend strings are never passed to KaTeX. KaTeX escapes its input and runs with
 * trust disabled, so the generated HTML contains no executable content. If a template fails to
 * render, the plain-language fallback is shown instead of raw LaTeX.
 */
import katex from "katex";
import { type ReactNode, useMemo } from "react";

export function MathEquation({ tex, display = false, fallback, label }: { tex: string; display?: boolean; fallback?: string; label?: string }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(tex, { displayMode: display, throwOnError: true, trust: false, strict: "ignore", output: "htmlAndMathml" });
    } catch {
      return null;
    }
  }, [tex, display]);
  if (html === null) return <span className="text-muted">{fallback ?? label ?? "Formula unavailable"}</span>;
  return display
    ? <div className="max-w-full overflow-x-auto overflow-y-hidden py-1 text-[15px]" aria-label={label} dangerouslySetInnerHTML={{ __html: html }} />
    : <span className="text-[14px]" aria-label={label} dangerouslySetInnerHTML={{ __html: html }} />;
}

export interface FormulaSpec {
  title: string;
  tex: string;
  vars: [string, string][];
  calc?: string | null;
  calcLabel?: string;
  result?: ReactNode;
  meaning?: ReactNode;
  fallback: string;
}

/** Formula → variables → substituted values → result → meaning. */
export function Formula({ spec }: { spec: FormulaSpec }) {
  return (
    <figure className="rounded-md border border-line bg-surface p-3">
      <figcaption className="text-[13px] font-semibold">{spec.title}</figcaption>
      <MathEquation tex={spec.tex} display fallback={spec.fallback} label={spec.fallback} />
      <dl className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[13px]">
        {spec.vars.map(([sym, meaning]) => (
          <div key={sym} className="contents"><dt className="text-right"><MathEquation tex={sym} /></dt><dd className="text-muted">{meaning}</dd></div>
        ))}
      </dl>
      {spec.calc && (
        <div className="mt-2 border-t border-line pt-2">
          <p className="label">{spec.calcLabel ?? "With the recorded numbers"}</p>
          <MathEquation tex={spec.calc} display fallback="Values not available" />
        </div>
      )}
      {spec.result && <p className="mt-1 text-[13.5px]"><span className="font-medium">Result: </span>{spec.result}</p>}
      {spec.meaning && <p className="mt-1 text-[13.5px] leading-relaxed">{spec.meaning}</p>}
    </figure>
  );
}
