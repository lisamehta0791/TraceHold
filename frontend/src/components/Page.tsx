import { motion } from 'motion/react';
import type { ReactNode } from 'react';
import { ease } from '../lib/motion';

/** Page transition inside the app: a short, quiet fade with a small rise. */
export function Page({ children }: { children: ReactNode }) {
  return (
    <motion.div
      className="page"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0, transition: { duration: 0.35, ease } }}
      exit={{ opacity: 0, transition: { duration: 0.15 } }}
    >
      {children}
    </motion.div>
  );
}

export function PageHead({ eyebrow, title, lede, right }: { eyebrow?: string; title: ReactNode; lede?: ReactNode; right?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow" style={{ marginBottom: 6 }}>{eyebrow}</div>}
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
      </div>
      {right && <div className="row wrap">{right}</div>}
    </div>
  );
}
