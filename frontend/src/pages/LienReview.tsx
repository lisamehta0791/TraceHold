import { motion } from 'motion/react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../api';
import type { LienFlag, LienItem } from '../types';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Chip, ToggleChip } from '../components/Chip';
import { ErrorCard } from '../components/ErrorCard';
import { IconChevron, IconChevronLeft, IconHand } from '../components/Icons';
import { PageHead } from '../components/Page';
import { PageSkeleton, RowsSkeleton } from '../components/Skeleton';
import { BAR_RADIUS, ChartTip, axisProps, gridProps, topLabel } from '../components/charts';
import { C, dateOnly, humanize, int, pct, ratio, rupeesCompact } from '../lib/format';
import { staggerParent } from '../lib/motion';
import { useAsync } from '../lib/useAsync';

const FLAGS: { key: LienFlag; label: string; sumKey?: string; color: string }[] = [
  { key: 'ALL', label: 'All restraints', color: C.ink },
  { key: 'OVER_HOLD', label: 'Over-hold', sumKey: 'over_hold', color: C.terracotta },
  { key: 'CLOSED_STILL_HELD', label: 'Closed, still held', sumKey: 'closed_still_held', color: C.oxblood },
  { key: 'PAST_90', label: 'Under ₹50k past 90 days', sumKey: 'past_90', color: C.saffron },
  { key: 'PAST_REVIEW', label: 'Past review date', sumKey: 'past_review', color: C.clay },
  { key: 'ESCALATE', label: 'Escalate', sumKey: 'escalate', color: C.rose },
];

const CLOSURE_COLOR: Record<string, string> = {
  OPEN: C.sand, UNDER_INVESTIGATION: C.saffron, CHARGESHEETED: C.olive, CLEAN_CHIT: C.terracotta, CLOSED: C.oxblood,
};

export default function LienReview() {
  const [flag, setFlag] = useState<LienFlag>('ALL');
  const [page, setPage] = useState(1);
  const q = useAsync(() => api.lienReview({ flag, page, page_size: 20 }), [flag, page]);
  const ov = useAsync(() => api.oversight(), []);
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / 20)) : 1;

  return (
    <motion.div variants={staggerParent} initial="hidden" animate="show">
      <PageHead
        eyebrow="Lien review queue"
        title="Holds that deserve a second look"
        lede={q.data ? `Existing restraints ranked by over-hold, age and case status, as of ${dateOnly(q.data.as_of)}.` : 'Existing restraints ranked by over-hold, age and case status.'}
      />
      <div className="note ox mb">
        <IconHand size={16} />
        <span><b>Ranked for human review — performs no release.</b> Ranking only orders the queue; every decision on a restraint stays with an authorised officer.</span>
      </div>

      <div className="chiprow mb">
        {FLAGS.map((f) => (
          <ToggleChip key={f.key} on={flag === f.key} color={f.color} onClick={() => { setFlag(f.key); setPage(1); }}
            count={f.key === 'ALL' ? (flag === 'ALL' ? q.data?.total : undefined) : f.sumKey ? q.data?.summary[f.sumKey] : undefined}>
            {f.label}
          </ToggleChip>
        ))}
      </div>

      {q.error ? <ErrorCard error={q.error} onRetry={q.reload} /> : !q.data ? <div className="card"><RowsSkeleton rows={10} /></div> : (
        <div className="card" style={{ padding: 0, opacity: q.loading ? 0.6 : 1, transition: 'opacity .2s' }}>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Scrollable table">
            <table className="ledger lien-table" style={{ minWidth: 1020 }}>
              <thead><tr><th className="r">#</th><th>Account · case</th><th className="r">Held</th><th>Supported</th><th style={{ minWidth: 200 }}>Over-hold (held ÷ upper)</th>
                <th className="r">Days held</th><th>90-day clock</th><th>Escalation</th><th>Closure</th><th>Flags</th></tr></thead>
              <tbody>
                {q.data.items.map((it, i) => <LienRow key={it.restraint_id} it={it} rank={(page - 1) * 20 + i + 1} i={i} />)}
              </tbody>
            </table>
            {q.data.items.length === 0 && <p className="muted" style={{ padding: 24, textAlign: 'center' }}>Nothing in this queue.</p>}
          </div>
          <div className="row between" style={{ padding: '12px 16px', borderTop: '1px solid var(--paper-3)' }}>
            <span className="small muted">{int(q.data.total)} restraints · page {page} of {pages}</span>
            <div className="row">
              <Button size="sm" icon={<IconChevronLeft size={15} />} disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next <IconChevron size={15} /></Button>
            </div>
          </div>
        </div>
      )}

      <div className="page-head mt-l" style={{ marginBottom: 14 }}>
        <div>
          <div className="eyebrow">Oversight</div>
          <h2>How holds are distributed</h2>
        </div>
      </div>
      {ov.error ? <ErrorCard error={ov.error} onRetry={ov.reload} /> : !ov.data ? <PageSkeleton tiles={2} panels={2} /> : (
        <motion.div variants={staggerParent} initial="hidden" animate="show" className="stack" style={{ gap: 18 }}>
          <div className="grid g4">
            <Card><div className="stat"><span className="label">Requests missing a required field</span><span className="value">{pct(ov.data.missing_fields_share, 0)}</span></div></Card>
            <Card><div className="stat"><span className="label">Restraints with no status update</span><span className="value">{pct(ov.data.no_update_share, 0)}</span></div></Card>
            <Card className="span2" title="By closure status" sub="Average over-hold ratio">
              <div className="stack" style={{ gap: 6 }}>
                {ov.data.by_status.map((s) => (
                  <div key={s.closure_status} className="row between small">
                    <Chip color={CLOSURE_COLOR[s.closure_status] ?? C.clay}>{humanize(s.closure_status)}</Chip>
                    <span className="num muted">{int(s.n)} holds</span>
                    <span className="num" style={{ fontWeight: 650, width: 60, textAlign: 'right' }}>{ratio(s.avg_over_hold)}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
          <div className="grid g2">
            <Card title="Over-hold ratio" sub="Held amount ÷ supported upper bound">
              <Hist data={ov.data.over_hold_hist} colorFor={(b, i) => (i === 0 ? C.olive : b.includes('50') ? C.oxblood : C.terracotta)} />
            </Card>
            <Card title="Age of holds" sub="Days since the restraint was placed">
              <Hist data={ov.data.age_hist} colorFor={() => C.clay} />
            </Card>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}

function Hist({ data, colorFor }: { data: { bucket: string; n: number }[]; colorFor: (b: string, i: number) => string }) {
  return (
    <div style={{ height: 230 }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 16, right: 6, left: -12, bottom: 0 }} barCategoryGap="18%">
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="bucket" {...axisProps} />
          <YAxis {...axisProps} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}K` : v)} width={44} />
          <Tooltip content={<ChartTip fmt={(v) => `${int(v)} holds`} />} cursor={{ fill: 'rgba(205,180,138,0.18)' }} />
          <Bar dataKey="n" name="Holds" radius={BAR_RADIUS} maxBarSize={40} animationDuration={800} label={topLabel((v) => int(v))}>
            {data.map((d, i) => <Cell key={d.bucket} fill={colorFor(d.bucket, i)} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function Ring({ days, total = 90 }: { days: number; total?: number }) {
  const r = 13; const circ = 2 * Math.PI * r;
  const left = Math.max(0, days);
  const frac = Math.min(1, left / total);
  const col = days <= 0 ? C.terracotta : days < 15 ? C.saffron : C.olive;
  return (
    <div className="row" style={{ gap: 6 }} title={days <= 0 ? `${-days} days past the 90-day mark` : `${days} days until 90 days`}>
      <svg width={34} height={34} viewBox="0 0 34 34">
        <circle cx={17} cy={17} r={r} fill="none" stroke={C.paper3} strokeWidth={4} />
        <motion.circle cx={17} cy={17} r={r} fill="none" stroke={col} strokeWidth={4} strokeLinecap="round" transform="rotate(-90 17 17)"
          strokeDasharray={circ} initial={{ strokeDashoffset: circ }} animate={{ strokeDashoffset: circ * (1 - (days <= 0 ? 1 : frac)) }} transition={{ duration: 1, ease: [0.2, 0.8, 0.2, 1] }} />
        <text x={17} y={20.5} textAnchor="middle" className="ring-label" fill={C.ink} fontSize={9.5} fontWeight={600}>{days <= 0 ? '!' : days}</text>
      </svg>
      <span className="tiny muted">{days <= 0 ? `${-days}d past` : 'days left'}</span>
    </div>
  );
}

function LienRow({ it, rank, i }: { it: LienItem; rank: number; i: number }) {
  const r = it.over_hold_ratio;
  const w = r === null ? 1 : Math.min(1, Math.log10(Math.max(1, r)) / 2); // log scale: 1x → 0, 100x → full
  return (
    <motion.tr initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0, transition: { delay: i * 0.02 } }}>
      <td className="r num mute2">{rank}</td>
      <td>
        <div className="mono small" style={{ fontWeight: 600 }}>{it.account_id}</div>
        <Link to={`/cases/${it.case_id}`} className="tiny mono" style={{ whiteSpace: 'nowrap' }}>{it.case_ref}</Link>
      </td>
      <td className="r num">{rupeesCompact(it.held_amount)}</td>
      <td className="num small muted" style={{ whiteSpace: 'nowrap' }}>{rupeesCompact(it.lower)}–{rupeesCompact(it.upper)}</td>
      <td>
        <div className="row" style={{ gap: 8 }}>
          <div className="rangebar" style={{ flex: 1, height: 8 }}>
            <motion.div className="fill" style={{ left: 0, background: r !== null && r <= 1.05 ? C.olive : r !== null && r < 3 ? C.saffron : C.terracotta }}
              initial={{ width: 0 }} animate={{ width: `${Math.max(3, w * 100)}%` }} transition={{ duration: 0.8, delay: i * 0.02 }} />
          </div>
          <span className="num small" style={{ width: 54, textAlign: 'right', fontWeight: 650 }}>{r === null ? '∞' : ratio(r)}</span>
        </div>
      </td>
      <td className="r num">{it.days_held}<div className="tiny mute2" style={{ whiteSpace: 'nowrap' }}>upd. {it.days_since_update}d ago</div></td>
      <td>{it.band === 'UNDER_50K' && it.days_to_90 !== null ? <Ring days={it.days_to_90} /> : <span className="tiny mute2">≥ ₹50k</span>}</td>
      <td className="small" style={{ whiteSpace: 'nowrap' }}>{dateOnly(it.escalation_date)}</td>
      <td><Chip color={CLOSURE_COLOR[it.closure_status] ?? C.clay}>{humanize(it.closure_status)}</Chip></td>
      <td style={{ minWidth: 128, maxWidth: 150 }}><div className="row wrap" style={{ gap: 3 }}>{it.flags.map((f) => <span key={f} className="chip plain" style={{ fontSize: 10.5 }}>{humanize(f)}</span>)}</div></td>
    </motion.tr>
  );
}
