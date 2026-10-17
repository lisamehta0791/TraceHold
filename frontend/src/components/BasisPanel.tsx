import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../api';
import type { BasisRule, BasisStep } from '../types';
import { IconChevron, IconCopy } from './Icons';
import { copyText } from '../lib/download';

/** What a result is based on: facts, the rules applied, and every SQL step that ran in Exasol. */
export function BasisPanel({ facts, rules, steps, where, query, queryTitle }: {
  facts: { label: string; value: ReactNode }[];
  rules: BasisRule[];
  steps: BasisStep[];
  where: 'cases' | 'playground';
  query?: string;
  queryTitle?: string;
}) {
  const totalMs = steps.reduce((s, x) => s + x.ms, 0);
  return (
    <div className="basis">
      <div className="basis-facts">
        {facts.map((f) => <div key={f.label}><b>{f.value}</b><span>{f.label}</span></div>)}
      </div>

      <div className="basis-cols">
        <div>
          <h3 className="basis-h">Rules applied</h3>
          <dl className="basis-rules">
            {rules.map((r) => (
              <div key={r.rule}>
                <dt>{r.rule}</dt>
                <dd><b>{r.value}</b><span>{r.why}</span></dd>
              </div>
            ))}
          </dl>
        </div>
        <div>
          <h3 className="basis-h">SQL that ran in Exasol <span>{steps.length} steps · {(totalMs / 1000).toFixed(1)} s</span></h3>
          <ol className="basis-steps">
            {steps.map((s, i) => <Step key={i} n={i + 1} s={s} where={where} />)}
          </ol>
        </div>
      </div>

      {query && (
        <div className="basis-query">
          <h3 className="basis-h">{queryTitle ?? 'Query this page reads'}</h3>
          <SqlBlock sql={query} />
        </div>
      )}
    </div>
  );
}

function Step({ n, s, where }: { n: number; s: BasisStep; where: 'cases' | 'playground' }) {
  const [open, setOpen] = useState(false);
  const [sql, setSql] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const toggle = () => {
    setOpen((o) => !o);
    if (!sql && s.file) api.sqlScript(s.file, where).then((r) => setSql(r.sql)).catch((e: Error) => setErr(e.message));
  };
  const passes = s.passes && s.pass_rows ? s.pass_rows.filter((x): x is number => x != null) : null;
  return (
    <li className={open ? 'open' : ''}>
      <button className="basis-step" onClick={toggle} disabled={!s.file}>
        <span className="basis-n">{n}</span>
        <span className="basis-main">
          <b>{s.step}</b>
          <span>{s.purpose}</span>
          {passes && passes.length > 0 && (
            <span className="basis-passes">
              Repeated {s.passes} times until nothing changed · rows per pass {passes.map((r) => r.toLocaleString('en-IN')).join(' → ')}
            </span>
          )}
        </span>
        <span className="basis-meta">
          <span className="mono">{s.ms >= 1000 ? `${(s.ms / 1000).toFixed(1)} s` : `${Math.round(s.ms)} ms`}</span>
          {s.file && <span className="basis-file mono">{s.file}<IconChevron size={12} /></span>}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }} style={{ overflow: 'hidden' }}>
            {err ? <p className="tiny" style={{ color: 'var(--terracotta)', padding: '8px 0' }}>{err}</p>
              : sql ? <SqlBlock sql={sql} /> : <p className="tiny muted" style={{ padding: '8px 0' }}>Loading the script…</p>}
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

const KW = /\b(SELECT|FROM|WHERE|JOIN|LEFT|INNER|ON|AND|OR|NOT|GROUP BY|ORDER BY|PARTITION BY|OVER|AS|CASE|WHEN|THEN|ELSE|END|WITH|UNION ALL|INSERT INTO|CREATE TABLE|DROP TABLE IF EXISTS|IF EXISTS|VALUES|SUM|COUNT|MIN|MAX|COALESCE|GREATEST|LEAST|ROWS BETWEEN|UNBOUNDED PRECEDING|CURRENT ROW|IN|IS|NULL|DISTINCT|LIMIT|EXP|LN|ROW_NUMBER|LAG|LEAD|UPDATE|SET|DELETE|MERGE INTO|USING|MATCHED)\b/g;

export function SqlBlock({ sql }: { sql: string }) {
  const [done, setDone] = useState(false);
  const lines = sql.split('\n');
  return (
    <div className="sql-block">
      <button className="sql-copy" onClick={async () => { await copyText(sql); setDone(true); setTimeout(() => setDone(false), 1400); }}>
        <IconCopy size={12} /> {done ? 'Copied' : 'Copy'}
      </button>
      <pre>
        {lines.map((l, i) => {
          const c = l.indexOf('--');
          const code = c >= 0 ? l.slice(0, c) : l;
          const comment = c >= 0 ? l.slice(c) : '';
          return <span key={i} className="sql-line">{highlight(code)}{comment && <span className="sql-c">{comment}</span>}{'\n'}</span>;
        })}
      </pre>
    </div>
  );
}

function highlight(code: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of code.matchAll(KW)) {
    if (m.index! > last) out.push(code.slice(last, m.index));
    out.push(<span key={m.index} className="sql-k">{m[0]}</span>);
    last = m.index! + m[0].length;
  }
  out.push(code.slice(last));
  return out;
}
