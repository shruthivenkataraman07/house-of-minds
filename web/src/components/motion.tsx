"use client";
/**
 * Motion that explains: numbers count up to the recorded value, steps light up in order.
 * Every component renders the final value immediately under prefers-reduced-motion, and each
 * named sequence plays once per visit (a page reload is a new visit).
 */
import { animate, motion, useInView, useReducedMotion } from "motion/react";
import { type ReactNode, useEffect, useRef, useState } from "react";

const played = new Set<string>();
export const EASE = [0.16, 1, 0.3, 1] as const;

/** True only the first time `key` is asked for during this visit. */
export function useFirstPlay(key: string): boolean {
  const reduce = useReducedMotion();
  const [first] = useState(() => !reduce && !played.has(key));
  useEffect(() => { played.add(key); }, [key]);
  return first;
}

/** Counts from 0 to `value` (display formatting only; the recorded value is never altered). */
export function CountUp({ value, format, delay = 0, duration = 0.7, play }: {
  value: number; format: (v: number) => string; delay?: number; duration?: number; play: boolean;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!play) { el.textContent = format(value); return; }
    el.textContent = format(0);
    const c = animate(0, value, { duration, delay, ease: EASE, onUpdate: (v) => { el.textContent = format(v); },
      onComplete: () => { el.textContent = format(value); } });
    return () => c.stop();
  }, [value, format, delay, duration, play]);
  return <span ref={ref} aria-label={format(value)}>{format(value)}</span>;
}

/** Fades content up once; `play=false` renders it in place. */
export function Reveal({ children, delay = 0, play, className = "" }: { children: ReactNode; delay?: number; play: boolean; className?: string }) {
  if (!play) return <div className={className}>{children}</div>;
  return (
    <motion.div className={className} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay, ease: EASE }}>
      {children}
    </motion.div>
  );
}

/** Plays a sequence once when scrolled into view. Returns [ref, active]. */
export function useInViewOnce<T extends Element>(key: string) {
  const ref = useRef<T>(null);
  const first = useFirstPlay(key);
  const seen = useInView(ref, { once: true, amount: 0.4 });
  return [ref, first ? seen : true, first] as const;
}
