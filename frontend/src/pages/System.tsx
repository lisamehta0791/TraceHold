import { AnimatePresence, motion } from 'motion/react';
import { Fragment, useEffect, useRef, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../api';
import type { RunDetail } from '../types';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Chip } from '../components/Chip';
import { ErrorCard } from '../components/ErrorCard';
import { IconCheck, IconDb, IconPlay } from '../components/Icons';
import { PageHead } from '../components/Page';
import { InsightsPanel } from './Insights';
import { AiAccuracy, AiCallLog } from './AiResults';
import { RunHistory } from './RunHistory';
import { ExasolFacts } from './ExasolFacts';
import { PageSkeleton, RowsSkeleton } from '../components/Skeleton';
import { Tabs } from '../components/Tabs';
import { BAR_RADIUS, axisProps, gridProps } from '../components/charts';
import { C, dateTime, int, pct } from '../lib/format';
import { staggerParent } from '../lib/motion';
import { useAsync } from '../lib/useAsync';

// older links pointed at tabs that have since been merged
const MERGED: Record<string, string> = { protect: 'runs', exasol: 'bench', ai: 'eval' };

export default function System() {
  const [tab, setTab] = useState(() => {
    const t = new URLSearchParams(window.location.search).get('tab') ?? 'eval';
    return MERGED[t] ?? t;
  });
  return (
    <div>
      <PageHead eyebrow="System · Exasol" title="Accuracy, insights, history and performance"
        lede="How well the engine performs on the 2,400 synthetic cases, what the results mean at scale, the record of everything that was run, and how fast Exasol does it." />
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'eval', label: 'Accuracy' }, { key: 'insights', label: 'Insights' }, { key: 'runs', label: 'Runs & history' }, { key: 'bench', label: 'Performance' }]} />
      <div style={{ paddingTop: 18 }}>
        {tab === 'eval' && <div className="stack" style={{ gap: 18 }}><Evaluation /><AiAccuracy /></div>}
        {tab === 'insights' && <InsightsPanel />}
        {tab === 'runs' && <div className="stack" style={{ gap: 18 }}><Runs /><RunHistory /><AiCallLog /></div>}
        {tab === 'bench' && <div className="stack" style={{ gap: 18 }}><Bench /><ExasolFacts /></div>}
      </div>
    </div>
  );
}

const statusColor = (s: string) => (s === 'DONE' ? C.olive : s === 'RUNNING' ? C.saffron : C.terracotta);

function Runs() {
  const list = useAsync(() => api.runs(), []);
  const [live, setLive] = useState<RunDetail | null>(null);
  const [startErr, setStartErr] = useState<Error | null>(null);
  const [starting, setStarting] = useState(false);
  const [expected, setExpected] = useState<number | null>(null);
  const poll = useRef<ReturnType<typeof setInterval>>();
  const [openRun, setOpenRun] = useState<number | null>(null);
  const [mode, setMode] = useState<'python' | 'lua'>('lua');

  useEffect(() => () => clearInterval(poll.current), []);

  const start = async () => {
    setStarting(true); setStartErr(null);
    try {
      // expected step count from the latest finished run (for the progress bar)
      const last = list.data?.runs.find((r) => r.status === 'DONE');
      if (last) api.run(last.run_id).then((d) => setExpected(d.steps.length)).catch(() => setExpected(null));
      const { run_id } = await api.startRun(mode);
      const tick = async () => {
        try {
          const d = await api.run(run_id);
          setLive(d);
          if (d.status !== 'RUNNING') { clearInterval(poll.current); list.reload(); }
        } catch (e) { clearInterval(poll.current); setStartErr(e as Error); }
      };
      await tick();
      clearInterval(poll.current);
      poll.current = setInterval(tick, 1000);
    } catch (e) { setStartErr(e as Error); } finally { setStarting(false); }
  };

  const running = live?.status === 'RUNNING';
  const progress = live ? (live.status === 'DONE' ? 1 : expected ? Math.min(0.97, live.steps.length / expected) : null) : 0;
  const totalMs = live ? live.steps.reduce((s, x) => s + x.ms, 0) : 0;

  return (
    <motion.div variants={staggerParent} initial="hidden" animate="show" className="stack" style={{ gap: 18 }}>
      <Card title="Run analysis" sub="Recomputes trails, sizing, classification and conservation checks inside Exasol"
        right={<Button variant="primary" icon={<IconPlay size={15} />} loading={starting || running} onClick={start}>{running ? 'Running in Exasol…' : 'Run analysis in Exasol'}</Button>}>
        <div className="row wrap" style={{ gap: 10, alignItems: 'center', marginBottom: 10 }}>
          <div className="seg" role="group" aria-label="How to run the analysis">
            {([['lua', 'One Exasol script'], ['python', 'Step by step from Python']] as const).map(([k, l]) => (
              <button key={k} className={mode === k ? 'on' : ''} aria-pressed={mode === k} onClick={() => setMode(k)} disabled={running}>
                {mode === k && <span className="seg-on" />}<span>{l}</span>
              </button>
            ))}
          </div>
          <span className="tiny muted">{mode === 'lua'
            ? 'EXECUTE SCRIPT TRACEHOLD.RUN_ANALYSIS(): every step and both repeat-until-stable loops run inside Exasol as one Lua script, generated from the same SQL files.'
            : 'Python sends each SQL step to Exasol and checks when the loops have stopped changing.'} Both give the same checksum.</span>
        </div>
        {startErr && <ErrorCard error={startErr} title="The run could not be started" onRetry={start} />}
        {!live && !startErr && <p className="small muted">Starts a new background run. Steps and timings stream in below as Exasol completes them.</p>}
        {live && (
          <div className="stack" style={{ gap: 12 }}>
            <div className="row between">
              <span className="row" style={{ gap: 8 }}><b className="num">Run #{live.run_id}</b><Chip color={statusColor(live.status)}>{live.status}</Chip></span>
              <span className="num small muted">{(totalMs / 1000).toFixed(1)} s in steps · {int(live.steps.reduce((s, x) => s + (x.rows ?? 0), 0))} rows</span>
            </div>
            <div className="rangebar" style={{ height: 8, overflow: 'hidden' }}>
              {progress === null ? (
                <motion.div className="fill" style={{ width: '30%', background: C.saffron }} animate={{ left: ['-30%', '100%'] }} transition={{ repeat: Infinity, duration: 1.4, ease: 'easeInOut' }} />
              ) : (
                <motion.div className="fill" style={{ left: 0, background: live.status === 'DONE' ? C.olive : C.saffron }} animate={{ width: `${progress * 100}%` }} transition={{ type: 'spring', stiffness: 80, damping: 20 }} />
              )}
            </div>
            <StepList steps={live.steps} running={running} />
          </div>
        )}
      </Card>

      <Card title="Audit log" sub="All analysis runs with snapshot, configuration and checksum">
        {list.error ? <ErrorCard error={list.error} onRetry={list.reload} /> : !list.data ? <RowsSkeleton rows={4} /> : (
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Scrollable table">
            <table className="ledger">
              <thead><tr><th>Run</th><th>Status</th><th>Started</th><th>Finished</th><th className="r">Duration</th><th>Snapshot</th><th>Checksum</th><th>Version</th><th /></tr></thead>
              <tbody>
                {list.data.runs.map((r) => (
                  <Fragment key={r.run_id}>
                    <tr key={r.run_id} className="clickable" onClick={() => setOpenRun(openRun === r.run_id ? null : r.run_id)}>
                      <td className="num">#{r.run_id}</td>
                      <td><Chip color={statusColor(r.status)}>{r.status}</Chip></td>
                      <td className="small">{dateTime(r.started)}</td>
                      <td className="small">{dateTime(r.finished)}</td>
                      <td className="r num">{r.duration_s != null ? `${r.duration_s.toFixed(1)} s` : '—'}</td>
                      <td className="mono tiny" title={r.snapshot_id ?? ''}>{short(r.snapshot_id)}</td>
                      <td className="mono tiny" title={r.checksum ?? ''}>{short(r.checksum)}</td>
                      <td className="tiny">{r.software_version ?? '—'}</td>
                      <td className="tiny mute2">{openRun === r.run_id ? 'hide' : 'details'}</td>
                    </tr>
                    {openRun === r.run_id && (
                      <tr key={`${r.run_id}-d`}><td colSpan={9}><RunDetailView id={r.run_id} config={r.config} /></td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </motion.div>
  );
}

const short = (s: string | null) => (s ? (s.length > 22 ? `${s.slice(0, 18)}…` : s) : '—');

function RunDetailView({ id, config }: { id: number; config: Record<string, unknown> | null }) {
  const { data, error, reload } = useAsync(() => api.run(id), [id]);
  return (
    <div className="stack" style={{ gap: 14, padding: '6px 0' }}>
      {data && (
        <div className="row wrap" style={{ gap: 8 }}>
          {data.source_unchanged != null && (
            <span className={`pill ${data.source_unchanged ? 'ok' : 'bad'}`}>{data.source_unchanged ? <IconCheck size={11} /> : null}
              {data.source_unchanged ? 'Source data unchanged by this run' : 'Source data changed during this run'}</span>
          )}
          {data.compared_with && (
            <span className={`pill ${data.compared_with.identical_results ? 'ok' : ''}`}>
              {data.compared_with.identical_results ? `Identical results to run #${data.compared_with.run_id}` : `Results differ from run #${data.compared_with.run_id}`}
              {data.compared_with.same_snapshot ? ' (same data)' : ' (different data)'}</span>
          )}
          {data.history_rows && data.history_rows.sizing > 0 && (
            <span className="pill">Kept in history: {int(data.history_rows.sizing)} account figures, {int(data.history_rows.review)} reviewed holds, {int(data.history_rows.trail)} trail transfers</span>
          )}
        </div>
      )}
      <div className="grid g2">
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Steps</div>
          {error ? <ErrorCard error={error} onRetry={reload} /> : !data ? <RowsSkeleton rows={4} /> : <StepList steps={data.steps} running={false} />}
        </div>
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Configuration</div>
          <pre className="draft" style={{ maxHeight: 280, overflow: 'auto' }}>{JSON.stringify(config ?? {}, null, 2)}</pre>
        </div>
      </div>
      {data?.fingerprints && data.fingerprints.length > 0 && (
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Source data before and after the run (row count and fingerprint)</div>
          <table className="ledger">
            <thead><tr><th>Table</th><th className="r">Rows before</th><th className="r">Rows after</th><th>Fingerprint before</th><th>Fingerprint after</th><th>Unchanged</th></tr></thead>
            <tbody>{data.fingerprints.map((f) => (
              <tr key={f.table}><td className="mono small">{f.table}</td><td className="r num small">{int(f.rows_before)}</td><td className="r num small">{int(f.rows_after)}</td>
                <td className="mono tiny">{f.fingerprint_before}</td><td className="mono tiny">{f.fingerprint_after}</td>
                <td>{f.unchanged ? <IconCheck size={13} /> : '✗'}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StepList({ steps, running }: { steps: RunDetail['steps']; running: boolean }) {
  const max = Math.max(1, ...steps.map((s) => s.ms));
  return (
    <div className="stack" style={{ gap: 4 }}>
      <AnimatePresence initial={false}>
        {steps.map((s, i) => (
          <motion.div key={`${s.step}-${i}`} layout initial={{ opacity: 0, x: -10, height: 0 }} animate={{ opacity: 1, x: 0, height: 'auto' }}
            style={{ display: 'grid', gridTemplateColumns: '22px minmax(160px, 1.3fr) 1fr 74px 120px', gap: 10, alignItems: 'center' }} className="small">
            <span className="check-icon" style={{ background: C.olive, width: 18, height: 18 }}><IconCheck size={11} /></span>
            <span>{s.step}</span>
            <div className="rangebar" style={{ height: 6 }}>
              <motion.div className="fill" style={{ left: 0, background: C.clay }} initial={{ width: 0 }} animate={{ width: `${(s.ms / max) * 100}%` }} transition={{ duration: 0.5 }} />
            </div>
            <span className="num r" style={{ textAlign: 'right' }}>{int(s.ms)} ms</span>
            <span className="num tiny mute2" style={{ textAlign: 'right' }}>{s.rows != null ? `${int(s.rows)} rows` : ''}</span>
          </motion.div>
        ))}
      </AnimatePresence>
      {running && (
        <div className="row small muted" style={{ gap: 10, paddingLeft: 2 }}>
          <span className="spinner" style={{ color: C.saffron }} /> working in Exasol…
        </div>
      )}
    </div>
  );
}

function Meter({ v, good = 0.95 }: { v: number; good?: number }) {
  return (
    <div className="row" style={{ gap: 8 }}>
      <div className="rangebar" style={{ width: 90, height: 7 }}>
        <motion.div className="fill" style={{ left: 0, background: v >= good ? C.olive : v >= 0.8 ? C.saffron : C.terracotta }} initial={{ width: 0 }} animate={{ width: `${Math.max(0, Math.min(1, v)) * 100}%` }} transition={{ duration: 0.8 }} />
      </div>
      <span className="num small">{pct(v, 1)}</span>
    </div>
  );
}

function Evaluation() {
  const { data, error, reload } = useAsync(() => api.evaluation(), []);
  if (error) return <ErrorCard error={error} onRetry={reload} />;
  if (!data) return <PageSkeleton tiles={4} panels={2} />;
  const ab = data.abstention;
  return (
    <motion.div variants={staggerParent} initial="hidden" animate="show" className="stack" style={{ gap: 18 }}>
      <div className="note"><span><b>{data.note.replace(/\.$/, '')}.</b> Scores against ground truth planted by the synthetic generator · generated {dateTime(data.generated_at)}.</span></div>
      <div className="grid g4">
        <Card><div className="stat"><span className="label">Conservation checks</span><span className="value">{int(data.conservation.passed)} / {int(data.conservation.checks)}</span><span className="sub">every convention accounts for the full loss</span></div></Card>
        <Card><div className="stat"><span className="label">Over-broad requests flagged</span><span className="value">{pct(data.overbroad.recall, 1)}</span><span className="sub">{int(data.overbroad.flagged)} of {int(data.overbroad.planted)} planted</span></div></Card>
        <Card><div className="stat"><span className="label">Correct abstention</span><span className="value">{pct(ab.correctly_undeterminable / Math.max(1, ab.planted), 1)}</span><span className="sub">{ab.correctly_undeterminable} of {ab.planted} undeterminable cases</span></div></Card>
        <Card><div className="stat"><span className="label">Wrongly abstained</span><span className="value">{pct(ab.wrongly_undeterminable / Math.max(1, ab.determinable), 2)}</span><span className="sub">{ab.wrongly_undeterminable} of {int(ab.determinable)} determinable</span></div></Card>
      </div>
      <div className="stack" style={{ gap: 18 }}>
        <Card title="Request defect detection" sub="CF1 completeness check">
          <table className="ledger">
            <thead><tr><th>Defect</th><th className="r">Planted</th><th className="r">Detected</th><th className="r">False +</th><th>Precision</th><th>Recall</th></tr></thead>
            <tbody>{data.request_defects.map((r) => (
              <tr key={r.defect}><td className="small">{r.defect.replace(/_/g, ' ').toLowerCase()}</td><td className="r num">{r.planted}</td><td className="r num">{r.detected}</td><td className="r num">{r.false_pos}</td><td><Meter v={r.precision} /></td><td><Meter v={r.recall} /></td></tr>
            ))}</tbody>
          </table>
        </Card>
        <Card title="Amount accuracy" sub="Sized amount vs generator ground truth, per convention">
          <table className="ledger">
            <thead><tr><th>Convention</th><th className="r">Mean abs. error</th><th className="r">Max abs. error</th><th>Within ₹1</th><th>Range coverage</th></tr></thead>
            <tbody>{data.amount.map((r) => (
              <tr key={r.convention}><td>{r.convention}</td><td className="r num">₹{r.mae.toFixed(2)}</td><td className="r num">₹{r.max_abs_err.toFixed(2)}</td><td><Meter v={r.within_1_rupee} /></td><td><Meter v={r.range_coverage} /></td></tr>
            ))}</tbody>
          </table>
        </Card>
      </div>
      <Card title="Trail reconstruction" sub="Path precision and recall by synthetic scenario">
        <table className="ledger">
          <thead><tr><th>Scenario</th><th className="r">TP</th><th className="r">FP</th><th className="r">FN</th><th>Precision</th><th>Recall</th></tr></thead>
          <tbody>{data.path.map((r) => (
            <tr key={r.scenario}><td className="small">{r.scenario.replace(/_/g, ' ').toLowerCase()}</td><td className="r num">{int(r.tp)}</td><td className="r num">{int(r.fp)}</td><td className="r num">{int(r.fn)}</td><td><Meter v={r.precision} /></td><td><Meter v={r.recall} /></td></tr>
          ))}</tbody>
        </table>
      </Card>
    </motion.div>
  );
}

const WORKLOADS: { key: string; name: string; what: string }[] = [
  { key: 'LOAD', name: 'Load', what: 'Bulk-load the CSV files into Exasol' },
  { key: 'W2', name: 'Full analysis', what: 'Clean every posting, rebuild every balance, trace and size every case' },
  { key: 'W1', name: 'One case', what: 'Trace and size a single case on the prepared ledger' },
  { key: 'W3', name: 'Lien review', what: 'Review queue and oversight totals over all restraints' },
];

function Bench() {
  const { data, error, reload } = useAsync(() => api.benchmark(), []);
  if (error) return <ErrorCard error={error} onRetry={reload} />;
  if (!data) return <PageSkeleton tiles={0} panels={3} />;
  const engines = [...new Set(data.results.map((r) => r.engine))].sort((a) => (a.toLowerCase().startsWith('exasol') ? -1 : 1));
  const hasPg = engines.some((e) => e.toLowerCase().startsWith('postgres'));
  const tiers = [...new Set(data.results.map((r) => r.tier))].sort((a, b) => 'SML'.indexOf(a) - 'SML'.indexOf(b));
  const size = (t: string) => data.results.find((r) => r.tier === t)?.rows ?? 0;
  const cell = (e: string, t: string, w: string) => data.results.find((r) => r.engine === e && r.tier === t && r.workload === w);
  const ex = engines.find((e) => e.toLowerCase().startsWith('exasol')) ?? 'Exasol';
  const pg = engines.find((e) => e.toLowerCase().startsWith('postgres'));
  const full = data.full_run;
  const bars = tiers.map((t) => {
    const o: Record<string, unknown> = { label: `${(size(t) / 1e6).toFixed(2)} M` };
    engines.forEach((e) => { o[e] = cell(e, t, 'W2')?.median_s ?? null; });
    return o;
  });
  if (full) bars.push({ label: `${(full.transactions / 1e6).toFixed(2)} M`, [ex]: full.core_s });
  const color = (e: string) => (e.toLowerCase().startsWith('exasol') ? C.oxblood : C.clay);
  const fmt = (x?: number | null) => (x == null ? '—' : x >= 10 ? `${x.toFixed(1)} s` : `${x.toFixed(2)} s`);
  const ratio = (t: string, w: string) => {
    const a = cell(ex, t, w)?.median_s, b = pg ? cell(pg, t, w)?.median_s : undefined;
    return a && b ? b / a : null;
  };
  const big = tiers[tiers.length - 1];
  return (
    <motion.div variants={staggerParent} initial="hidden" animate="show" className="stack" style={{ gap: 18 }}>
      <div className="note"><IconDb size={16} /><span>
        Same SQL, same data, same laptop (<b>{hwText(data.hardware)}</b>), each database alone in Docker with up to 4 GB of memory.
        Medians of repeated warm runs. PostgreSQL {hasPg ? 'is tuned (memory settings and the indexes a reasonable engineer would add); Exasol uses its defaults and builds its own indexes.' : 'was not measured.'}
      </span></div>

      <div className="grid g2" style={{ alignItems: 'stretch' }}>
        <Card title="Full analysis time as the data grows" sub="Clean every posting, rebuild balances, trace and size every case">
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={bars} margin={{ top: 16, right: 10, left: -8, bottom: 0 }} barCategoryGap="26%" barGap={4}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="label" {...axisProps} />
                <YAxis {...axisProps} tickFormatter={(v) => `${v}s`} width={48} />
                <Tooltip cursor={{ fill: 'rgba(205,180,138,0.18)' }} formatter={(v: number, n: string) => [`${Number(v).toFixed(1)} s`, n]} labelFormatter={(l) => `${l} transactions`} />
                {engines.map((e) => <Bar key={e} dataKey={e} name={e} radius={BAR_RADIUS} maxBarSize={44} animationDuration={800} fill={color(e)} />)}
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="row wrap small" style={{ gap: 14, marginTop: 6 }}>
            {engines.map((e) => <span key={e} className="row" style={{ gap: 6 }}><i style={{ width: 12, height: 12, borderRadius: 3, background: color(e), display: 'inline-block' }} />{e}</span>)}
          </div>
          <p className="tiny muted">Transactions on the x-axis.{full ? ` The 2.4 M point is Exasol only: analysis run #${full.run_id} on the full dataset.` : ''}</p>
        </Card>
        <Card title="What the numbers say">
          <ul className="clean stack small" style={{ gap: 8 }}>
            {pg && tiers.map((t) => ratio(t, 'W2') && (
              <li key={t}><span>· Full analysis on {int(size(t))} transactions: Exasol <b>{fmt(cell(ex, t, 'W2')?.median_s)}</b>, PostgreSQL <b>{fmt(cell(pg, t, 'W2')?.median_s)}</b>: <b>{ratio(t, 'W2')!.toFixed(1)}× faster</b> on Exasol.</span></li>
            ))}
            {pg && tiers.length >= 2 && (
              <li><span>· With {(size(big) / size(tiers[0])).toFixed(1)}× more data, Exasol's time grew {((cell(ex, big, 'W2')?.median_s ?? 0) / (cell(ex, tiers[0], 'W2')?.median_s ?? 1)).toFixed(1)}×, PostgreSQL's {((cell(pg, big, 'W2')?.median_s ?? 0) / (cell(pg, tiers[0], 'W2')?.median_s ?? 1)).toFixed(1)}×: the gap widens as the data grows.</span></li>
            )}
            {full && <li><span>· On all <b>{int(full.transactions)}</b> transactions Exasol's core analysis took <b>{Math.round(full.core_s)} s</b>.</span></li>}
            {pg && <li>· PostgreSQL is faster on small, quick queries (one case, the review queue, loading), where per-query overhead counts more than processing power; both answer those within seconds.</li>}
          </ul>
        </Card>
      </div>

      <Card title="All measurements" sub="median (min–max) over repeated warm runs">
        <div className="table-wrap" tabIndex={0} role="region" aria-label="All benchmark measurements">
          <table className="ledger">
            <thead><tr><th>Workload</th><th>What it does</th>{tiers.flatMap((t) => engines.map((e) => <th key={t + e} className="r">{e}<div className="tiny mute2">{int(size(t))} txns</div></th>))}</tr></thead>
            <tbody>
              {WORKLOADS.map((w) => (
                <tr key={w.key}>
                  <td><b>{w.name}</b></td><td className="small muted">{w.what}</td>
                  {tiers.flatMap((t) => engines.map((e) => {
                    const r = cell(e, t, w.key);
                    return <td key={t + e} className="r num">{fmt(r?.median_s)}{r && r.runs > 1 && <div className="tiny mute2">{fmt(r.min_s)}–{fmt(r.max_s)}</div>}</td>;
                  }))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="tiny muted" style={{ marginTop: 8 }}>Synthetic data only. Only these workloads were measured; no general claim is made about either database.</p>
      </Card>
    </motion.div>
  );
}

function hwText(h: unknown): string {
  if (!h) return 'this machine';
  if (typeof h === 'string') return h;
  const o = h as { cpu?: string; ram_gb?: number; cpu_count?: number };
  return [o.cpu, o.ram_gb ? `${o.ram_gb} GB RAM` : null, o.cpu_count ? `${o.cpu_count} logical CPUs` : null].filter(Boolean).join(', ');
}

