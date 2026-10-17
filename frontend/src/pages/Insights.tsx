import { motion } from 'motion/react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../api';
import { Card } from '../components/Card';
import { ToggleChip } from '../components/Chip';
import { ErrorCard } from '../components/ErrorCard';
import { PageSkeleton } from '../components/Skeleton';
import { Tabs } from '../components/Tabs';
import { BAR_RADIUS, ChartTip, Legend, axisProps, gridProps, topLabel } from '../components/charts';
import { C, SCENARIO_COLOR, compactNum, int, pct, rupeesCompact, scenarioLabel } from '../lib/format';
import { staggerParent } from '../lib/motion';
import { useAsync } from '../lib/useAsync';

/** The three analysis views used on the System page (Insights tab). */
export function InsightsPanel() {
  const [tab, setTab] = useState('policy');
  return (
    <div>
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'policy', label: 'What different hold policies would do' }, { key: 'speed', label: 'How fast money disappears' }, { key: 'sens', label: 'How much the method matters' }]} />
      <div style={{ paddingTop: 18 }}>
        {tab === 'policy' && <Policy />}
        {tab === 'speed' && <SpeedView />}
        {tab === 'sens' && <Sens />}
      </div>
    </div>
  );
}

function Policy() {
  const { data, error, reload } = useAsync(() => api.policySim(), []);
  const [policy, setPolicy] = useState<string | null>(null);
  if (error) return <ErrorCard error={error} onRetry={reload} />;
  if (!data) return <PageSkeleton tiles={0} panels={2} />;
  const chart = data.policies.map((p) => ({ name: p.label, disputed: p.disputed_held, other: p.non_disputed_locked, accounts: p.accounts_restricted, key: p.policy }));
  const sel = data.policies.find((p) => p.policy === policy) ?? data.policies[0];
  return (
    <motion.div variants={staggerParent} initial="hidden" animate="show" className="stack" style={{ gap: 18 }}>
      <div className="note"><span><b>{data.note}.</b> A what-if comparison at the {data.hold_time}. It describes outcomes of hypothetical policies — it does not recommend one.</span></div>
      <div className="grid g3">
        <Card className="span2" title="Disputed money held vs other money locked" sub="Per holding policy (₹)"
          right={<Legend items={[{ label: 'Disputed money held', color: C.olive }, { label: 'Non-disputed money locked', color: C.terracotta }]} />}>
          <div style={{ height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={chart} margin={{ top: 18, right: 8, left: 4, bottom: 0 }} barGap={3} barCategoryGap="26%">
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="name" {...axisProps} interval={0} />
                <YAxis {...axisProps} tickFormatter={(v) => compactNum(v)} width={58} />
                <Tooltip content={<ChartTip fmt={(v) => rupeesCompact(v)} />} cursor={{ fill: 'rgba(205,180,138,0.18)' }} />
                <Bar dataKey="disputed" name="Disputed money held" fill={C.olive} radius={BAR_RADIUS} maxBarSize={28} animationDuration={900}
                  label={topLabel((v) => rupeesCompact(v, 0))} />
                <Bar dataKey="other" name="Non-disputed money locked" fill={C.terracotta} radius={BAR_RADIUS} maxBarSize={28} animationDuration={900}
                  label={topLabel((v) => rupeesCompact(v, 0))} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Accounts restricted" sub="Per policy">
          <div className="stack" style={{ gap: 10 }}>
            {data.policies.map((p) => {
              const ratioOther = p.non_disputed_locked / Math.max(1, p.disputed_held + p.non_disputed_locked);
              return (
                <div key={p.policy}>
                  <div className="row between small"><span>{p.label}</span><span className="num">{int(p.accounts_restricted)}</span></div>
                  <div className="tiny mute2">{pct(ratioOther, 0)} of locked money is not disputed</div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
      <Card title="By synthetic scenario" sub="Pick a policy" right={
        <div className="chiprow">{data.policies.map((p) => <ToggleChip key={p.policy} on={sel.policy === p.policy} onClick={() => setPolicy(p.policy)}>{p.label}</ToggleChip>)}</div>
      }>
        <div style={{ height: 300 }}>
          <ResponsiveContainer>
            <BarChart data={sel.by_scenario.map((s) => ({ ...s, name: scenarioLabel(s.scenario) }))} layout="vertical" margin={{ top: 4, right: 20, left: 40, bottom: 0 }} barGap={2}>
              <CartesianGrid {...gridProps} horizontal={false} vertical />
              <XAxis type="number" {...axisProps} tickFormatter={(v) => compactNum(v)} />
              <YAxis type="category" dataKey="name" {...axisProps} width={120} />
              <Tooltip content={<ChartTip fmt={(v) => rupeesCompact(v)} />} cursor={{ fill: 'rgba(205,180,138,0.18)' }} />
              <Bar dataKey="disputed_held" name="Disputed money held" fill={C.olive} radius={[0, 4, 4, 0]} maxBarSize={12} animationDuration={800} />
              <Bar dataKey="non_disputed_locked" name="Non-disputed money locked" fill={C.terracotta} radius={[0, 4, 4, 0]} maxBarSize={12} animationDuration={800} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </motion.div>
  );
}

function SpeedView() {
  const { data, error, reload } = useAsync(() => api.speed(), []);
  const [off, setOff] = useState<Set<string>>(new Set());
  if (error) return <ErrorCard error={error} onRetry={reload} />;
  if (!data) return <PageSkeleton tiles={0} panels={1} />;
  const minutes = [...new Set(data.curves.flatMap((c) => c.points.map((p) => p.minutes)))].sort((a, b) => a - b);
  const rows = minutes.map((m) => {
    const r: Record<string, number> = { minutes: m };
    data.curves.forEach((c) => { const p = c.points.find((x) => x.minutes === m); if (p) r[c.scenario] = p.share_inside; });
    return r;
  });
  const toggle = (s: string) => setOff((o) => { const n = new Set(o); if (n.has(s)) n.delete(s); else n.add(s); return n; });
  const fmtMin = (m: number) => (m >= 60 ? `${+(m / 60).toFixed(1)} h` : `${m} min`);
  return (
    <motion.div variants={staggerParent} initial="hidden" animate="show">
      <Card title="Share of disputed money still inside observable accounts" sub="By minutes since the fraud (square-root time axis) · synthetic data"
        right={<div className="chiprow">{data.curves.map((c) => (
          <ToggleChip key={c.scenario} on={!off.has(c.scenario)} color={SCENARIO_COLOR[c.scenario] ?? C.clay} onClick={() => toggle(c.scenario)}>{c.scenario === 'ALL' ? 'All cases' : scenarioLabel(c.scenario)}</ToggleChip>
        ))}</div>}>
        <div style={{ height: 380 }}>
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ top: 10, right: 30, left: -4, bottom: 4 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="minutes" type="number" scale="sqrt" domain={[0, 'dataMax']} ticks={[0, 15, 60, 180, 360, 720, 1440].filter((t) => t <= minutes[minutes.length - 1])} tickFormatter={fmtMin} {...axisProps} />
              <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} {...axisProps} width={46} />
              <Tooltip content={<ChartTip fmt={(v) => pct(v, 0)} labelFmt={(l) => `${fmtMin(Number(l))} after the fraud`} />} cursor={{ stroke: C.clay }} />
              {data.curves.filter((c) => !off.has(c.scenario)).map((c) => (
                <Line key={c.scenario} dataKey={c.scenario} name={c.scenario === 'ALL' ? 'All cases' : scenarioLabel(c.scenario)} type="monotone"
                  stroke={SCENARIO_COLOR[c.scenario] ?? C.clay} strokeWidth={c.scenario === 'ALL' ? 3 : 2} dot={false}
                  activeDot={{ r: 5, stroke: C.paper2, strokeWidth: 2 }} animationDuration={900} strokeDasharray={c.scenario === 'ALL' ? undefined : undefined} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="small muted mt">Every minute counts: the steeper the early drop, the less a hold placed later can still reach. Rapid cash-out cases leave observable accounts almost immediately.</p>
      </Card>
    </motion.div>
  );
}

function Sens() {
  const { data, error, reload } = useAsync(() => api.sensitivity(), []);
  if (error) return <ErrorCard error={error} onRetry={reload} />;
  if (!data) return <PageSkeleton tiles={0} panels={2} />;
  return (
    <motion.div variants={staggerParent} initial="hidden" animate="show" className="stack" style={{ gap: 18 }}>
      <div className="grid g2">
        <Card title="How much do conventions disagree?" sub="Accounts by sensitivity: (max − min) ÷ max across PR, FIFO, LIFO">
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={data.hist} margin={{ top: 10, right: 6, left: -12, bottom: 0 }} barCategoryGap="12%">
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="bucket" {...axisProps} interval={1} />
                <YAxis {...axisProps} tickFormatter={(v) => compactNum(v)} width={44} />
                <Tooltip content={<ChartTip fmt={(v) => `${int(v)} accounts`} />} cursor={{ fill: 'rgba(205,180,138,0.18)' }} />
                <Bar dataKey="n" name="Accounts" fill={C.saffron} radius={BAR_RADIUS} maxBarSize={32} animationDuration={800} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Sensitivity grows with distance" sub="Average sensitivity by layer">
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={data.by_layer} margin={{ top: 18, right: 6, left: -12, bottom: 0 }} barCategoryGap="30%">
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="layer" {...axisProps} tickFormatter={(l) => `Layer ${l}`} />
                <YAxis {...axisProps} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={46} />
                <Tooltip content={<ChartTip fmt={(v) => pct(v, 0)} labelFmt={(l) => `Layer ${l}`} />} cursor={{ fill: 'rgba(205,180,138,0.18)' }} />
                <Bar dataKey="avg_sensitivity" name="Avg sensitivity" fill={C.oxblood} radius={BAR_RADIUS} maxBarSize={30} animationDuration={800}
                  label={topLabel((v) => pct(v, 0))} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
      <Card title="Most convention-sensitive accounts" sub="Where the choice of convention changes the answer the most — open the case to see why">
        <table className="ledger">
          <thead><tr><th>Case</th><th>Account</th><th className="r">Lowest (any convention)</th><th className="r">Highest (any convention)</th><th style={{ width: 220 }}>Sensitivity</th></tr></thead>
          <tbody>
            {data.top.map((t, i) => (
              <motion.tr key={`${t.case_id}-${t.account_id}`} initial={{ opacity: 0 }} animate={{ opacity: 1, transition: { delay: i * 0.03 } }}>
                <td><Link to={`/cases/${t.case_id}`} className="mono">#{t.case_id}</Link></td>
                <td className="mono small">{t.account_id}</td>
                <td className="r num">{rupeesCompact(t.lower_ext)}</td>
                <td className="r num">{rupeesCompact(t.upper_ext)}</td>
                <td>
                  <div className="row" style={{ gap: 8 }}>
                    <div className="rangebar" style={{ flex: 1, height: 8 }}>
                      <motion.div className="fill" style={{ left: 0, background: C.oxblood }} initial={{ width: 0 }} animate={{ width: `${t.sensitivity * 100}%` }} transition={{ duration: 0.8, delay: i * 0.03 }} />
                    </div>
                    <span className="num small">{pct(t.sensitivity, 0)}</span>
                  </div>
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </Card>
    </motion.div>
  );
}
