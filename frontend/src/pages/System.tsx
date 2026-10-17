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
import { AiPanel } from './AiPanel';
import { PageSkeleton, RowsSkeleton } from '../components/Skeleton';
import { Tabs } from '../components/Tabs';
import { BAR_RADIUS, axisProps, gridProps } from '../components/charts';
import { C, dateTime, int, pct } from '../lib/format';
import { staggerParent } from '../lib/motion';
import { useAsync } from '../lib/useAsync';

export default function System() {
  const [tab, setTab] = useState('eval');
  return (
    <div>
      <PageHead eyebrow="System · Exasol" title="Accuracy, insights, runs and AI"
        lede="How well the engine performs on the 2,400 synthetic cases, what the results mean at scale, and the record of every analysis run." />
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'eval', label: 'Accuracy' }, { key: 'insights', label: 'Insights' }, { key: 'runs', label: 'Runs & audit log' }, { key: 'bench', label: 'Benchmark' }, { key: 'ai', label: 'AI' }]} />
      <div style={{ paddingTop: 18 }}>
        {tab === 'runs' && <Runs />}
        {tab === 'eval' && <Evaluation />}
        {tab === 'insights' && <InsightsPanel />}
        {tab === 'bench' && <Bench />}
        {tab === 'ai' && <AiPanel />}
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

  useEffect(() => () => clearInterval(poll.current), []);

  const start = async () => {
    setStarting(true); setStartErr(null);
    try {
      // expected step count from the latest finished run (for the progress bar)
      const last = list.data?.runs.find((r) => r.status === 'DONE');
      if (last) api.run(last.run_id).then((d) => setExpected(d.steps.length)).catch(() => setExpected(null));
      const { run_id } = await api.startRun();
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
          <div className="table-wrap">
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
    <div className="grid g2" style={{ padding: '6px 0' }}>
      <div>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Steps</div>
        {error ? <ErrorCard error={error} onRetry={reload} /> : !data ? <RowsSkeleton rows={4} /> : <StepList steps={data.steps} running={false} />}
      </div>
      <div>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Configuration</div>
        <pre className="draft" style={{ maxHeight: 280, overflow: 'auto' }}>{JSON.stringify(config ?? {}, null, 2)}</pre>
      </div>
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
      <div className="note"><span><b>{data.note}.</b> Scores against ground truth planted by the synthetic generator · generated {dateTime(data.generated_at)}.</span></div>
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
  const ex = data.results.filter((r) => r.engine.toLowerCase().startsWith('exasol'));
  const tiers = [...new Set(ex.map((r) => r.tier))];
  const size = (t: string) => ex.find((r) => r.tier === t)?.rows ?? 0;
  const cell = (t: string, w: string) => ex.find((r) => r.tier === t && r.workload === w);
  const full = data.full_run;
  const bars = [
    ...tiers.map((t) => ({ label: `${(size(t) / 1e6).toFixed(2)} M`, secs: cell(t, 'W2')?.median_s ?? 0, kind: 'bench' })),
    ...(full ? [{ label: `${(full.transactions / 1e6).toFixed(2)} M`, secs: full.core_s, kind: 'run' }] : []),
  ];
  const fmt = (x?: number) => (x == null ? '—' : x >= 10 ? `${x.toFixed(1)} s` : `${x.toFixed(2)} s`);
  return (
    <motion.div variants={staggerParent} initial="hidden" animate="show" className="stack" style={{ gap: 18 }}>
      <div className="note"><IconDb size={16} /><span>
        Measured on <b>{hwText(data.hardware)}</b>, Exasol Personal in Docker with a 3–4 GB memory limit. Each figure is the median of repeated runs.
        Exasol only: a PostgreSQL comparison was planned, but both databases do not fit in this laptop's memory at the same time, so no comparison is claimed.
      </span></div>

      <div className="grid g2" style={{ alignItems: 'stretch' }}>
        <Card title="Full analysis time as the data grows" sub="Clean, rebuild balances, trace and size every case">
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={bars} margin={{ top: 16, right: 10, left: -8, bottom: 0 }} barCategoryGap="30%">
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="label" {...axisProps} />
                <YAxis {...axisProps} tickFormatter={(v) => `${v}s`} width={48} />
                <Tooltip cursor={{ fill: 'rgba(205,180,138,0.18)' }} formatter={(v: number) => [`${v.toFixed(1)} s`, 'time']} labelFormatter={(l) => `${l} transactions`} />
                <Bar dataKey="secs" radius={BAR_RADIUS} maxBarSize={56} animationDuration={800} fill={C.oxblood} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="tiny muted">Transactions on the x-axis.{full ? ` The largest point is analysis run #${full.run_id} on the full dataset (whole run including request checks and reviews: ${Math.round(full.duration_s)} s).` : ''}</p>
        </Card>
        <Card title="What the numbers say">
          <ul className="clean stack small" style={{ gap: 8 }}>
            {bars.length >= 2 && <li>· Data grew <b>{(size(tiers[tiers.length - 1]) / Math.max(1, size(tiers[0]))).toFixed(1)}×</b> from {int(size(tiers[0]))} to {int(size(tiers[tiers.length - 1]))} transactions; the full analysis took <b>{(bars[tiers.length - 1].secs / Math.max(0.01, bars[0].secs)).toFixed(1)}×</b> as long.</li>}
            {full && <li>· On all <b>{int(full.transactions)}</b> transactions the core analysis took <b>{Math.round(full.core_s)} s</b>, entirely inside Exasol as set-based SQL.</li>}
            <li>· Sizing one case on the prepared ledger takes seconds, and the lien-review queue over every restraint under a second.</li>
            <li>· The live analysis page runs the same SQL on a small case in about 5–15 s.</li>
          </ul>
        </Card>
      </div>

      <Card title="All measurements" sub="median (min–max) over repeated runs">
        <div className="table-wrap">
          <table className="ledger">
            <thead><tr><th>Workload</th><th>What it does</th>{tiers.map((t) => <th key={t} className="r">{int(size(t))} txns</th>)}</tr></thead>
            <tbody>
              {WORKLOADS.map((w) => (
                <tr key={w.key}>
                  <td><b>{w.name}</b></td><td className="small muted">{w.what}</td>
                  {tiers.map((t) => {
                    const r = cell(t, w.key);
                    return <td key={t} className="r num">{fmt(r?.median_s)}{r && r.runs > 1 && <div className="tiny mute2">{fmt(r.min_s)}–{fmt(r.max_s)} · n={r.runs}</div>}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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

