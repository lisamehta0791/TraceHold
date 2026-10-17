import { motion } from 'motion/react';
import type { PgStep } from '../types';
import { rupees } from '../lib/format';

/** Posting-by-posting explanation of how an account's disputed amount was calculated. */
export function CalcTimeline({ steps, opening, account }: { steps: PgStep[]; opening?: number; account: string }) {
  return (
    <ol className="timeline">
      {opening !== undefined && (
        <li className="tl-item start">
          <span className="tl-dot" />
          <div><b>Start</b><p>Account {account} already held {rupees(opening)} of its own money.</p></div>
        </li>
      )}
      {steps.map((s, i) => (
        <motion.li key={s.txn_id + i} className={`tl-item ${s.kind}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
          transition={{ delay: Math.min(i, 12) * 0.05, duration: 0.3 }}>
          <span className="tl-dot" />
          <div style={{ flex: 1 }}>
            <div className="row between wrap" style={{ gap: 8 }}>
              <b>{s.when ?? ''} · {s.kind === 'IN' ? 'Money in' : 'Money out'}</b>
              <span className="mono tiny muted">balance after {rupees(s.balance_after)}</span>
            </div>
            <p>{s.text}</p>
            {s.calc && (
              <div className="calc-pair">
                <div className="calc pr"><span>Pro-rata</span>{s.calc.pro_rata}</div>
                <div className="calc ff"><span>FIFO</span>{s.calc.fifo}</div>
              </div>
            )}
            <div className="tl-after mono tiny">disputed money now: pro-rata {rupees(s.disputed_pr_after)} · FIFO {rupees(s.disputed_fifo_after)}</div>
          </div>
        </motion.li>
      ))}
    </ol>
  );
}
