import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';
import { api } from '../api';
import type { AskResult } from '../types';
import { Button } from '../components/Button';
import { ErrorCard } from '../components/ErrorCard';
import { IconAlert, IconCheck, IconDb, IconSpark } from '../components/Icons';
import { PageHead } from '../components/Page';
import { SqlBlock } from '../components/BasisPanel';
import { useAsync } from '../lib/useAsync';

const fmtCell = (v: unknown) => {
  if (v === null || v === undefined) return '—';
  const s = String(v);
  if (/^-?\d+\.\d+$/.test(s)) return Number(s).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  return s;
};

export default function Ask() {
  const tpl = useAsync(() => api.askTemplates(), []);
  const status = useAsync(() => api.aiStatus(), []);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const [history, setHistory] = useState<AskResult[]>([]);

  const ask = async (question: string) => {
    const text = question.trim();
    if (!text) return;
    setBusy(true); setErr(null); setQ(text);
    try {
      const r = await api.ask(text);
      setHistory((h) => [r, ...h].slice(0, 8));
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };

  const off = status.data && !status.data.llm.enabled;

  return (
    <div>
      <PageHead eyebrow="Questions over the results · Exasol MCP server" title="Ask the results"
        lede="Ask in plain English. The answer comes from a read-only query on the analysis results, and the query and its rows are always shown." />

      <section className="an-block">
        <form className="ask-box" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Which holds older than 120 days exceed their supported amount?"
            maxLength={500} disabled={busy || !!off} />
          <Button variant="primary" icon={<IconSpark size={15} />} loading={busy} disabled={!q.trim() || !!off} onClick={() => ask(q)}>Ask</Button>
        </form>
        {off && <div className="note" style={{ marginTop: 12 }}><IconAlert size={15} /><span>AI is off ({status.data!.llm.reason}). Everything else in TraceHold works without it.</span></div>}
        <div className="ask-suggest">
          {(tpl.data?.templates ?? []).map((t) => (
            <button key={t.id} className="chip-btn" disabled={busy || !!off} onClick={() => ask(t.question.replace(' N days', ' 90 days').replace(' X times', ' 5 times'))}>
              {t.question}
            </button>
          ))}
        </div>
        <p className="tiny muted" style={{ marginTop: 10 }}>
          How it is governed: the model picks a prepared query or drafts one SELECT; a rule check allows only the results views
          ({(tpl.data?.views ?? []).map((v) => v.name).join(', ')}); the query runs through Exasol's MCP server as a read-only
          database user that cannot see raw transactions or the answer key; any number in the wording must appear in the rows.
        </p>
      </section>

      {err && <ErrorCard error={err} title="The question could not be answered" />}

      <AnimatePresence initial={false}>
        {history.map((r, i) => (
          <motion.section key={`${r.question}-${history.length - i}`} className="an-block ask-result"
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
            <div className="ask-q">{r.question}</div>
            <p className="ask-a">{r.answer}</p>
            <div className="row wrap" style={{ gap: 8, margin: '6px 0 14px' }}>
              <span className="pill">{r.mode === 'TEMPLATE' ? `Prepared query: ${r.template_id}` : r.mode === 'SQL' ? 'Query written by the AI, checked by rules' : 'Refused'}</span>
              {r.mode !== 'REFUSED' && (
                <span className={`pill ${r.fidelity.ok ? 'ok' : 'bad'}`}>
                  {r.fidelity.ok ? <IconCheck size={12} /> : <IconAlert size={12} />}
                  {r.fidelity.ok ? 'Every number is in the rows' : `Wording rejected: ${r.fidelity.unsupported.join(', ')}`}
                </span>
              )}
              {r.via && <span className="pill"><IconDb size={12} /> {r.via}</span>}
              {r.ms != null && <span className="tiny muted">{(r.ms / 1000).toFixed(1)} s</span>}
            </div>
            {r.sql && <SqlBlock sql={r.sql} />}
            {r.columns.length > 0 && (
              <div className="table-wrap" tabIndex={0} role="region" aria-label="Scrollable table" style={{ maxHeight: 360, marginTop: 12 }}>
                <table className="ledger">
                  <thead><tr>{r.columns.map((c) => <th key={c}>{c.toLowerCase().replace(/_/g, ' ')}</th>)}</tr></thead>
                  <tbody>{r.rows.slice(0, 200).map((row, k) => <tr key={k}>{row.map((v, j) => <td key={j} className="small mono">{fmtCell(v)}</td>)}</tr>)}</tbody>
                </table>
              </div>
            )}
            <p className="tiny muted" style={{ marginTop: 8 }}>{r.row_count} row(s){r.row_count >= 200 ? ' (row limit reached)' : ''}. Synthetic data.</p>
          </motion.section>
        ))}
      </AnimatePresence>
    </div>
  );
}
