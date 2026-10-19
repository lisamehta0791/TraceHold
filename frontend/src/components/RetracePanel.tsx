import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';
import { api } from '../api';
import type { RetraceResult } from '../types';
import { Button } from './Button';
import { ErrorCard } from './ErrorCard';
import { IconAlert, IconCheck, IconPlay } from './Icons';
import { plainStep, rupees } from '../lib/format';

/** Re-runs this one case inside Exasol on the full ledger and checks the figures against the stored results. */
export function RetracePanel({ caseId }: { caseId: number }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<RetraceResult | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [t0, setT0] = useState(0);
  const run = async () => {
    setBusy(true); setErr(null); setRes(null); setT0(Date.now());
    try { setRes(await api.retrace(caseId)); } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  return (
    <div className="retrace">
      <div className="row between wrap" style={{ gap: 10 }}>
        <div>
          <b>Re-trace this case live in Exasol</b>
          <div className="tiny muted">Follows the money again on the full ledger of all transactions and compares every figure with the stored result.</div>
        </div>
        <Button variant="primary" size="sm" icon={<IconPlay size={14} />} loading={busy} onClick={run}>{busy ? 'Tracing in Exasol…' : res ? 'Run again' : 'Re-trace now'}</Button>
      </div>
      <AnimatePresence>
        {busy && <motion.p className="tiny muted" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>Running the trail, sizing and conservation SQL for this case… (started {new Date(t0).toLocaleTimeString()})</motion.p>}
      </AnimatePresence>
      {err && <ErrorCard error={err} title="The re-trace could not run" />}
      {res && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="stack" style={{ gap: 10, marginTop: 10 }}>
          <div className="retrace-figs">
            <div><b>{(res.ms / 1000).toFixed(1)} s</b><span>inside Exasol</span></div>
            <div><b>{res.ledger_transactions.toLocaleString('en-IN')}</b><span>transactions in the ledger</span></div>
            <div><b>{res.layers}</b><span>passes until the trail stopped changing</span></div>
            <div className={res.identical ? 'good' : 'bad'}><b>{res.identical ? 'Identical' : 'Different'}</b><span>to the stored result ({res.accounts.length} accounts)</span></div>
          </div>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Re-traced figures">
            <table className="ledger">
              <thead><tr><th>Account</th><th className="r">Layer</th><th className="r">Pro-rata</th><th className="r">FIFO</th><th className="r">Supported range</th><th>Status</th><th>Same as stored</th></tr></thead>
              <tbody>{res.accounts.map((a) => (
                <tr key={a.account_id}><td className="mono small">{a.account_id}</td><td className="r num small">{a.layer}</td>
                  <td className="r num small">{rupees(a.retained_pr)}</td><td className="r num small">{rupees(a.retained_fifo)}</td>
                  <td className="r num small">{rupees(a.lower)} – {rupees(a.upper)}</td><td className="small">{a.status}</td>
                  <td>{a.matches_stored ? <IconCheck size={13} /> : <IconAlert size={13} />}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <p className="tiny muted">Steps: {res.steps.map((s) => `${plainStep(s.step)} (${(s.ms / 1000).toFixed(1)} s)`).join(' · ')}. Ran in the scratch schema {res.schema}; stored results were not touched.</p>
        </motion.div>
      )}
    </div>
  );
}
