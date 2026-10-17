import { useEffect, useState } from 'react';
import { api } from '../api';
import type { HoldDraftResult, HoldItem } from '../types';
import { Button } from './Button';
import { ErrorCard } from './ErrorCard';
import { IconCopy, IconDownload } from './Icons';
import { copyText, downloadText } from '../lib/download';
import { rupees } from '../lib/format';

const BASES: { key: 'LOWER' | 'UPPER' | 'CUSTOM'; label: string; hint: string }[] = [
  { key: 'LOWER', label: 'Lower end', hint: 'traceable under both counting methods' },
  { key: 'UPPER', label: 'Upper end', hint: 'traceable under at least one method' },
  { key: 'CUSTOM', label: 'Choose per account', hint: 'any amount up to the upper end' },
];

/** Turns the analysis into the document a bank needs: a hold limited to what the records support, per account. */
export function HoldDraft({ caseId, live }: {
  caseId?: number;
  live?: { case_ref: string; ref_time: string; request: Record<string, unknown>; items: HoldItem[] };
}) {
  const [basis, setBasis] = useState<'LOWER' | 'UPPER' | 'CUSTOM'>('UPPER');
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [res, setRes] = useState<HoldDraftResult | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    const t = window.setTimeout(() => {
      const call = caseId != null ? api.caseHoldDraft(caseId, basis, overrides)
        : api.holdDraft({ ...live!, basis, overrides });
      call.then((r) => { if (alive) { setRes(r); setErr(null); } }).catch((e) => alive && setErr(e));
    }, 250);
    return () => { alive = false; window.clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, basis, JSON.stringify(overrides), JSON.stringify(live?.items)]);

  if (err) return <ErrorCard error={err} title="The draft could not be prepared" />;
  if (!res) return <p className="small muted">Preparing the draft…</p>;
  if (res.plan.length === 0) return <p className="small muted">The request names no accounts, so there is nothing to hold.</p>;
  const t = res.totals;
  return (
    <div className="hold">
      <div className="hold-top">
        <div className="seg" role="group" aria-label="Basis for the proposed hold">
          {BASES.map((b) => (
            <button key={b.key} className={basis === b.key ? 'on' : ''} aria-pressed={basis === b.key} onClick={() => setBasis(b.key)} title={b.hint}>
              {basis === b.key && <span className="seg-on" />}<span>{b.label}</span>
            </button>
          ))}
        </div>
        <span className="tiny muted">{BASES.find((b) => b.key === basis)!.hint}</span>
      </div>
      <div className="hold-sum">
        <div><span>Requested</span><b>{rupees(t.requested)}</b></div>
        <div><span>Proposed hold</span><b>{rupees(t.proposed)}</b></div>
        <div className="good"><span>Not restricted (account holders' own money)</span><b>{rupees(t.released)}</b></div>
      </div>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Proposed hold per account">
        <table className="ledger">
          <thead><tr><th>Account</th><th className="r">Requested</th><th className="r">Supported by the records</th><th className="r">Proposed hold</th><th className="r">Not restricted</th></tr></thead>
          <tbody>{res.plan.map((p) => (
            <tr key={p.account_id}>
              <td className="mono small">{p.account_id}</td>
              <td className="r num small">{rupees(p.requested)}</td>
              <td className="r num small">{p.upper == null ? '—' : `${rupees(p.lower)} – ${rupees(p.upper)}`}</td>
              <td className="r num small">
                {p.proposed == null ? <span className="tiny muted">{p.note}</span>
                  : basis === 'CUSTOM' ? (
                    <input className="hold-input" type="number" min={0} max={p.upper ?? undefined} step="0.01" aria-label={`Proposed hold for ${p.account_id}`}
                      value={overrides[p.account_id] ?? p.proposed} onChange={(e) => setOverrides({ ...overrides, [p.account_id]: Number(e.target.value) })} />
                  ) : <b>{rupees(p.proposed)}</b>}
              </td>
              <td className="r num small">{p.released == null ? '—' : rupees(p.released)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <details className="draft" open>
        <summary>Draft hold instruction</summary>
        <pre>{res.text}</pre>
        <div className="row" style={{ gap: 8 }}>
          <Button size="sm" icon={<IconCopy size={14} />} onClick={async () => { await copyText(res.text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? 'Copied' : 'Copy text'}</Button>
          <Button size="sm" icon={<IconDownload size={14} />} onClick={() => downloadText('proportionate-hold-draft.txt', res.text)}>Download .txt</Button>
        </div>
      </details>
      <p className="tiny muted">A draft for the reviewing officer: amounts never exceed what was requested or what the records support, and nothing is sent automatically.</p>
    </div>
  );
}
