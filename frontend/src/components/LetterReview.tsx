import { AnimatePresence, motion } from 'motion/react';
import { useMemo, useState } from 'react';
import type { Extraction, ExtractField, ExtractStatus } from '../types';
import { Button } from './Button';
import { IconAlert, IconCheck, IconConflict, IconX } from './Icons';
import { rupees } from '../lib/format';

export const FIELD_ORDER = ['officer', 'designation', 'agency', 'contact', 'case_reference', 'legal_provision', 'quoted_txn',
  'stated_amount', 'action_type', 'targets'];

const STATUS: Record<ExtractStatus, { label: string; cls: string }> = {
  VERIFIED: { label: 'Checked', cls: 'ok' },
  PARTLY: { label: 'Partly checked', cls: 'warn' },
  UNVERIFIED: { label: 'Failed checks: not used', cls: 'bad' },
  CONFLICT: { label: 'Conflict: not resolved', cls: 'bad' },
  NOT_STATED: { label: 'Not stated', cls: 'none' },
};

const ACTIONS: Record<string, string> = { TOTAL_FREEZE: 'Freeze the whole account', DEBIT_FREEZE: 'Block debits', LIEN_AMOUNT: 'Hold a stated amount' };

export type ConfirmedFields = Record<string, string | number | string[] | null>;

function initialValue(f: ExtractField): string {
  if (f.status !== 'VERIFIED' && f.status !== 'PARTLY') return '';
  if (Array.isArray(f.value)) return f.value.join(', ');
  return f.value == null ? '' : String(f.value);
}

/** Shows the letter with each quoted span highlighted, the fields with their checks, and lets a person confirm them. */
export function LetterReview({ ex, onConfirm, confirmLabel = 'Confirm these fields', recordValues }: {
  ex: Extraction;
  onConfirm: (fields: ConfirmedFields, by: string) => Promise<void> | void;
  confirmLabel?: string;
  recordValues?: Record<string, string | null>;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(ex.fields.map((f) => [f.field, initialValue(f)])));
  const [by, setBy] = useState('');
  const [hover, setHover] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const fields = useMemo(() => FIELD_ORDER.map((k) => ex.fields.find((f) => f.field === k)).filter(Boolean) as ExtractField[], [ex]);

  const segments = useMemo(() => {
    const spans: { start: number; end: number; field: string; status: ExtractStatus }[] = [];
    for (const f of ex.fields) for (const it of f.items) if (it.start >= 0) spans.push({ start: it.start, end: it.end, field: f.field, status: it.verified ? f.status : 'UNVERIFIED' });
    spans.sort((a, b) => a.start - b.start);
    const out: { text: string; field?: string; status?: ExtractStatus }[] = [];
    let pos = 0;
    for (const s of spans) {
      if (s.start < pos) continue;
      if (s.start > pos) out.push({ text: ex.text.slice(pos, s.start) });
      out.push({ text: ex.text.slice(s.start, s.end), field: s.field, status: s.status });
      pos = s.end;
    }
    out.push({ text: ex.text.slice(pos) });
    return out;
  }, [ex]);

  const confirm = async () => {
    setBusy(true);
    const out: ConfirmedFields = {};
    for (const f of fields) {
      const v = (values[f.field] ?? '').trim();
      if (f.field === 'targets') out[f.field] = v ? v.split(/[,;\s]+/).filter(Boolean).map((x) => x.toUpperCase()) : [];
      else if (f.field === 'stated_amount') out[f.field] = v === '' ? null : Number(v.replace(/,/g, ''));
      else out[f.field] = v || null;
    }
    try { await onConfirm(out, by.trim() || 'reviewer'); setDone(true); } finally { setBusy(false); }
  };

  const nOk = fields.filter((f) => f.status === 'VERIFIED').length;
  const nBad = fields.filter((f) => f.status === 'UNVERIFIED' || f.status === 'CONFLICT').length;

  return (
    <div className="lr">
      <div className="lr-head">
        <span><b>{nOk}</b> of {fields.length} fields checked · <b>{nBad}</b> flagged · <b>{fields.length - nOk - nBad}</b> not stated</span>
        <span className="tiny muted">Read by {ex.model} ({ex.prompt_version}) in {(ex.ms / 1000).toFixed(1)} s · every value was then checked by fixed rules</span>
      </div>
      <div className="lr-grid">
        <div className="lr-letter">
          <div className="lr-cap">The letter, with the text each value came from highlighted</div>
          <pre>
            {segments.map((s, i) => s.field
              ? <mark key={i} className={`lr-mark ${STATUS[s.status!].cls} ${hover === s.field ? 'hot' : ''}`} title={s.field}
                onMouseEnter={() => setHover(s.field!)} onMouseLeave={() => setHover(null)}>{s.text}</mark>
              : <span key={i}>{s.text}</span>)}
          </pre>
        </div>
        <div className="lr-fields">
          {fields.map((f) => {
            const st = STATUS[f.status];
            const failed = f.items.flatMap((it) => it.checks.filter((c) => !c.ok));
            return (
              <div key={f.field} className={`lr-field ${hover === f.field ? 'hot' : ''}`} onMouseEnter={() => setHover(f.field)} onMouseLeave={() => setHover(null)}>
                <div className="lr-row">
                  <span className="lr-label">{f.label.split(/[(:,]/)[0]}</span>
                  <span className={`lr-chip ${st.cls}`}>
                    {st.cls === 'ok' ? <IconCheck size={11} /> : f.status === 'CONFLICT' ? <IconConflict size={11} /> : st.cls === 'none' ? null : <IconAlert size={11} />}
                    {st.label}
                  </span>
                </div>
                {f.field === 'action_type' ? (
                  <select value={values[f.field] ?? ''} disabled={done} onChange={(e) => setValues({ ...values, [f.field]: e.target.value })}>
                    <option value="">— not stated —</option>
                    {Object.entries(ACTIONS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                ) : (
                  <input value={values[f.field] ?? ''} disabled={done} placeholder={f.status === 'NOT_STATED' ? 'not stated in the letter' : 'not used: type the correct value if you know it'}
                    onChange={(e) => setValues({ ...values, [f.field]: e.target.value })} />
                )}
                {f.field === 'stated_amount' && values[f.field] && !Number.isNaN(Number(values[f.field])) && <span className="tiny muted">{rupees(Number(values[f.field]))}</span>}
                {recordValues && f.field in recordValues && (
                  <span className="tiny muted">Structured record says: <b>{recordValues[f.field] ?? 'not stated'}</b></span>
                )}
                {f.items.length > 0 && (
                  <button className="lr-more" onClick={() => setOpen(open === f.field ? null : f.field)}>
                    {open === f.field ? 'Hide checks' : `Checks (${failed.length ? `${failed.length} failed` : 'all passed'})`}
                  </button>
                )}
                <AnimatePresence initial={false}>
                  {open === f.field && (
                    <motion.div className="lr-checks" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
                      {f.reasons.map((r, i) => <p key={i} className="tiny">{r}</p>)}
                      {f.items.map((it, i) => (
                        <div key={i} className="lr-item">
                          <span className="mono tiny">“{it.span || '—'}”</span>
                          <ul>{it.checks.map((c, j) => (
                            <li key={j} className={c.ok ? 'ok' : 'bad'}>{c.ok ? <IconCheck size={10} /> : <IconX size={10} />} {c.check}{c.detail ? `: ${c.detail}` : ''}</li>
                          ))}</ul>
                        </div>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </div>
      <div className="lr-confirm">
        {done ? (
          <span className="pill ok"><IconCheck size={13} /> Confirmed and saved in Exasol</span>
        ) : (
          <>
            <input className="lr-by" value={by} onChange={(e) => setBy(e.target.value)} placeholder="Your name (recorded with the confirmation)" />
            <Button variant="primary" loading={busy} onClick={confirm}>{confirmLabel}</Button>
            <span className="tiny muted">A person confirms every field. Flagged fields stay empty unless you type the correct value.</span>
          </>
        )}
      </div>
    </div>
  );
}
