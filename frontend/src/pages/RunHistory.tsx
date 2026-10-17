import { useState } from 'react';
import { api } from '../api';
import type { RunCompare } from '../types';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { ErrorCard } from '../components/ErrorCard';
import { IconAlert, IconCheck, IconRefresh, IconShield } from '../components/Icons';
import { RowsSkeleton } from '../components/Skeleton';
import { dateTime, rupees } from '../lib/format';
import { useAsync } from '../lib/useAsync';

/** History kept in Exasol beyond the audit log, and the live proof that it cannot be damaged. */
export function RunHistory() {
  const prot = useAsync(() => api.protection(), []);
  const runs = useAsync(() => api.runs(), []);
  const live = useAsync(() => api.liveAnalyses(20), []);
  const done = (runs.data?.runs ?? []).filter((r) => r.status === 'DONE');
  const [a, setA] = useState<number | ''>('');
  const [b, setB] = useState<number | ''>('');
  const [cmp, setCmp] = useState<RunCompare | null>(null);
  const [cmpErr, setCmpErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const runA = a === '' ? done[1]?.run_id : a;
  const runB = b === '' ? done[0]?.run_id : b;

  const compare = async () => {
    if (runA == null || runB == null) return;
    setBusy(true); setCmpErr(null);
    try { setCmp(await api.compareRuns(runA, runB)); } catch (e) { setCmpErr(e as Error); } finally { setBusy(false); }
  };

  const p = prot.data;
  return (
    <div className="stack" style={{ gap: 18 }}>
      <Card title="Compare two runs" sub="Every run's results are kept in the history; any two can be compared account by account">
        {done.length < 2 ? <p className="small muted">At least two finished runs are needed. Start one above.</p> : (
          <div className="stack" style={{ gap: 10 }}>
            <div className="row wrap" style={{ gap: 10, alignItems: 'center' }}>
              <label className="small">Run <select className="input" value={runA ?? ''} onChange={(e) => setA(Number(e.target.value))}>
                {done.map((r) => <option key={r.run_id} value={r.run_id}>#{r.run_id} · {dateTime(r.started)}</option>)}</select></label>
              <label className="small">with run <select className="input" value={runB ?? ''} onChange={(e) => setB(Number(e.target.value))}>
                {done.map((r) => <option key={r.run_id} value={r.run_id}>#{r.run_id} · {dateTime(r.started)}</option>)}</select></label>
              <Button size="sm" variant="primary" loading={busy} onClick={compare}>Compare</Button>
            </div>
            {cmpErr && <ErrorCard error={cmpErr} />}
            {cmp && (
              <div className={`note ${cmp.identical ? 'olive' : ''}`}>
                {cmp.identical ? <IconCheck size={15} /> : <IconAlert size={15} />}
                <span className="small">
                  Run #{cmp.a}: {cmp.rows_a.toLocaleString('en-IN')} account figures · run #{cmp.b}: {cmp.rows_b.toLocaleString('en-IN')}.{' '}
                  {cmp.rows_a === 0 || cmp.rows_b === 0 ? 'One of these runs finished before the history was kept, so there is nothing to compare.'
                    : <>{cmp.changed.toLocaleString('en-IN')} figures differ and {cmp.reclassified.toLocaleString('en-IN')} requested holds were classified differently.{cmp.identical ? ' The results are identical.' : ''}</>}
                </span>
              </div>
            )}
          </div>
        )}
      </Card>

      <Card title="Live analyses" sub="Every case run on the Live analysis page, with what was entered and what came out">
        {live.error ? <ErrorCard error={live.error} /> : !live.data ? <RowsSkeleton rows={4} /> : live.data.analyses.length === 0 ? (
          <p className="small muted">No live analyses yet.</p>
        ) : (
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Scrollable table" style={{ maxHeight: 380 }}>
            <table className="ledger">
              <thead><tr><th>When (UTC)</th><th>Reference</th><th className="r">Stolen</th><th className="r">Asked to hold</th><th className="r">Traced (pro-rata / FIFO)</th><th>Request</th><th>Money accounted for</th></tr></thead>
              <tbody>{live.data.analyses.map((x) => (
                <tr key={x.analysis_id}>
                  <td className="small">{dateTime(x.created)}</td>
                  <td className="mono tiny">{x.case_title}</td>
                  <td className="r num small">{rupees(x.summary.loss)}</td>
                  <td className="r num small">{rupees(x.summary.totals?.requested)}</td>
                  <td className="r num small">{rupees(x.summary.totals?.traced_pr)} / {rupees(x.summary.totals?.traced_fifo)}</td>
                  <td className="small">{x.summary.request_status ?? '—'}</td>
                  <td>{x.summary.conservation_ok ? <IconCheck size={13} /> : '—'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Try to break it" sub={`Statements that would damage source data or history, sent to Exasol as ${p?.engine_user ?? 'the analysis user'}`}
        right={<Button size="sm" icon={<IconRefresh size={14} />} loading={prot.loading} onClick={prot.reload}>Run the checks again</Button>}>
        {!p?.checks ? (prot.loading ? <RowsSkeleton rows={6} /> : null) : (
          <>
            <div className={`note ${p.all_ok ? 'olive' : ''}`} style={{ marginBottom: 12 }}>
              {p.all_ok ? <IconShield size={15} /> : <IconAlert size={15} />}
              <span className="small">{p.all_ok
                ? 'Exasol refused every attempt to delete or change source data, history or the answer key, and allowed only reading.'
                : 'At least one check did not behave as expected; see below.'}</span>
            </div>
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Scrollable table">
              <table className="ledger">
                <thead><tr><th>Attempt</th><th>Statement</th><th>Result</th><th>What Exasol said</th></tr></thead>
                <tbody>{p.checks.map((c) => (
                  <tr key={c.statement}>
                    <td className="small"><b>{c.action}</b></td>
                    <td className="mono tiny">{c.statement}</td>
                    <td><span className={`pill ${c.ok ? 'ok' : 'bad'}`}>{c.ok ? <IconCheck size={11} /> : <IconAlert size={11} />}{c.result}</span></td>
                    <td className="tiny muted">{c.exasol_says}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </>
        )}
      </Card>

    </div>
  );
}
