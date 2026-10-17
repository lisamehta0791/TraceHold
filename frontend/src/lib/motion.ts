import { useReducedMotion } from 'motion/react';
import type { Variants } from 'motion/react';

/**
 * Shared motion language: short, soft and purposeful. Movement only ever
 * explains something (where content came from, what changed) and never
 * repeats on its own.
 */
export const ease = [0.22, 1, 0.36, 1] as const;

export const staggerParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05, delayChildren: 0.04 } },
};

export const riseIn: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease } },
};

export function useMotionOK() {
  return !useReducedMotion();
}
