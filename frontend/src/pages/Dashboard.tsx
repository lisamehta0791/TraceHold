import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../api';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { ChartTip, Legend, axisProps, gridProps } from '../components/charts';
import { ErrorCard } from '../components/ErrorCard';
import { HBars } from '../components/HBars';
import { IconEngine, IconShield } from '../components/Icons';
import { PageHead } from '../components/Page';
import { PageSkeleton } from '../components/Skeleton';
import { StatTile } from '../components/StatTile';
import {
  C, CLASS_COLOR, CLASS_LABEL, REQ_COLOR, REQ_LABEL, SCENARIO_COLOR, STATUS_COLOR, STATUS_LABEL, dateTime, int, pct, rupeesCompact, scenarioLabel,
} from '../lib/format';
import { staggerParent } from '../lib/motion';
import { useAsync } from '../lib/useAsync';

export default function Dashboard({ embedded = false }: { embedded?: boolean }) {
  const { data, error, reload } = useAsync(() => api.overview(), []);
  const nav = useNavigate();
  if (error) return <ErrorCard error={error} onRetry={reload} />;
  if (!data) return <PageSkeleton tiles={4} panels={4} />;
  const t = data.totals;
  const consOK = data.conservation.passed === data.conservation.checks;
  const layerData = data.layer_profile.map((l) => ({ ...l, gap: [l.avg_share_pr, l.avg_share_fifo] as [number, number] }));

  return (
    <motion.div variants={staggerParent} initial="hidden" animate="show">
      {embedded ? (
        <div className="row" style={{ justifyContent: 'flex-end', marginBottom: 14 }}>
          <motion.span
            className="chip tint"
            style={{ ['--c' as string]: consOK ? C.olive : C.terracotta, padding: '6px 12px', fontSize: 12.5 } as React.CSSProperties}
            initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: 'spring', delay: 0.4 }}
            title="Every convention must account for the full loss: retained + exited + dust + absorbed = loss"
          >
            <IconShield size={15} /> Conservation <span className="num">{int(data.conservation.passed)} / {int(data.conservation.checks)}</span> checks passed
          </motion.span>
        </div>
      ) : (
      <PageHead
        eyebrow="Overview · all synthetic cases"
        title="What the records support"
        lede="Totals across every case in the current analysis run. Supported figures are ranges under disclosed conventions — they are not instructions to hold or release anything."
        right={
          <motion.span
            className="chip tint"
            style={{ ['--c' as string]: consOK ? C.olive : C.terracotta, padding: '6px 12px', fontSize: 12.5 } as React.CSSProperties}
            initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: 'spring', delay: 0.4 }}
            title="Every convention must account for the full loss: retained + exited + dust + absorbed = loss"
          >
            <IconShield size={15} /> Conservation <span className="num">{int(data.conservation.passed)} / {int(data.conservation.checks)}</span> checks passed
          </motion.span>
        }
      />
      )}

      <motion.div className="grid g4" variants={staggerParent}>
        <StatTile label="Reported loss" value={t.reported_loss} format={(v) => rupeesCompact(v)} sub={`${int(data.counts.cases)} cases · ${int(data.counts.requests)} requests`} swatch={C.ink} />
        <StatTile label="Requested to hold" value={t.requested_total} format={(v) => rupeesCompact(v)} sub={`${int(data.counts.request_targets)} account targets`} swatch={C.clay} />
        <StatTile label="Supported range" value={t.supported_upper} format={(v) => `${rupeesCompact(t.supported_lower)} – ${rupeesCompact(v)}`} sub="lower – upper bound, summed over accounts" swatch={C.saffron} small />
        <StatTile label="Locked without support" value={t.unsupported_locked} format={(v) => rupeesCompact(v)} sub={`${pct(t.unsupported_locked / Math.max(1, t.whole_balance_locked), 0)} of whole balances locked`} swatch={C.oxblood} accent={C.oxblood} />
      </motion.div>

      <motion.div className="grid g3 mt" variants={staggerParent}>
        <Card className="span2" title="Locked vs supported" sub="Whole-balance freezing versus what the records can support (₹)">
          <HBars
            format={(v) => rupeesCompact(v)}
            data={[
              { key: 'whole', label: 'Whole balances locked', value: t.whole_balance_locked, color: C.terracotta },
              { key: 'req', label: 'Requested', value: t.requested_total, color: C.clay },
              { key: 'loss', label: 'Reported loss', value: t.reported_loss, color: C.inkSoft },
              { key: 'upper', label: 'Supported — upper bound', value: t.supported_upper, color: C.saffron },
              { key: 'lower', label: 'Supported — lower bound', value: t.supported_lower, color: C.olive },
            ]}
          />
          <div className="note ox mt">
            <span>
              Whole-balance holds lock <b className="num">{(t.whole_balance_locked / Math.max(1, t.supported_upper)).toFixed(1)}×</b> the supported upper bound.
              The gap is the account holders’ own money, frozen without a traced link to the reported loss.
            </span>
          </div>
        </Card>
        <Card title="Latest run" sub="Analysis computed in Exasol" right={<Button size="sm" variant="ghost" icon={<IconEngine size={15} />} onClick={() => nav('/engine')}>Engine room</Button>}>
          {data.run ? (
            <div className="stack" style={{ gap: 8 }}>
              <div className="row between"><span className="muted small">Run</span><span className="num">#{data.run.run_id}</span></div>
              <div className="row between"><span className="muted small">Status</span><span className="chip tint" style={{ ['--c' as string]: data.run.status === 'DONE' ? C.olive : C.saffron } as React.CSSProperties}><span className="dot" />{data.run.status}</span></div>
              <div className="row between"><span className="muted small">Started</span><span className="num small">{dateTime(data.run.started)}</span></div>
              <div className="row between"><span className="muted small">Duration</span><span className="num">{data.run.duration_s?.toFixed(1) ?? '—'} s</span></div>
              <hr className="divider" />
              <div className="row between"><span className="muted small">Accounts</span><span className="num">{int(data.counts.accounts)}</span></div>
              <div className="row between"><span className="muted small">Transactions</span><span className="num">{int(data.counts.transactions)}</span></div>
              <div className="row between"><span className="muted small">Institutions</span><span className="num">{int(data.counts.institutions)}</span></div>
              <div className="row between"><span className="muted small">Restraints</span><span className="num">{int(data.counts.restraints)}</span></div>
            </div>
          ) : <p className="muted small">No analysis run yet.</p>}
        </Card>
      </motion.div>

      <motion.div className="grid g3 mt" variants={staggerParent}>
        <Card title="Request vs evidence" sub="Classification of each requested account">
          <HBars showShare data={data.classification_breakdown.map((d) => ({
            key: d.classification, label: CLASS_LABEL[d.classification], value: d.n, color: CLASS_COLOR[d.classification], hatch: d.classification === 'CANNOT_DETERMINE',
          }))} />
        </Card>
        <Card title="Sizing status" sub="How firmly each account could be sized">
          <HBars showShare data={data.status_breakdown.map((d) => ({
            key: d.status, label: STATUS_LABEL[d.status], value: d.n, color: STATUS_COLOR[d.status], hatch: d.status === 'UNDETERMINABLE', dashed: d.status === 'OUT_OF_SCOPE',
          }))} />
        </Card>
        <Card title="Request completeness" sub="Checked before any sizing">
          <HBars showShare data={data.request_status_breakdown.map((d) => ({
            key: d.request_status, label: REQ_LABEL[d.request_status], value: d.n, color: REQ_COLOR[d.request_status],
          }))} />
          <p className="tiny mute2 mt">Incomplete or conflicting requests get a drafted clarification on the case page.</p>
        </Card>
      </motion.div>

      <motion.div className="grid g3 mt" variants={staggerParent}>
        <Card className="span2" title="Dilution by layer" sub="Average share of an account’s balance traceable to the loss, by hops from the victim"
          right={<Legend items={[{ label: 'FIFO', color: C.saffron, kind: 'line' }, { label: 'Pro-rata', color: C.oxblood, kind: 'line' }]} />}>
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <ComposedChart data={layerData} margin={{ top: 10, right: 46, bottom: 4, left: -6 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="layer" {...axisProps} tickFormatter={(l) => `L${l}`} />
                <YAxis {...axisProps} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={44} />
                <Tooltip content={<ChartTip fmt={(v) => (Array.isArray(v) ? '' : pct(v))} labelFmt={(l) => `Layer ${l}`} />} cursor={{ stroke: C.clay, strokeWidth: 1 }} />
                <Area type="monotone" dataKey="gap" stroke="none" fill={C.saffron} fillOpacity={0.12} isAnimationActive name="Convention gap" legendType="none" activeDot={false} tooltipType="none" />
                <Line type="monotone" dataKey="avg_share_fifo" name="FIFO" stroke={C.saffron} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: C.paper2, fill: C.saffron }} animationDuration={900}
                  label={(p: { x: number; y: number; index: number; value: number }) => p.index === layerData.length - 1 ? <text x={p.x + 8} y={p.y + 4} fontSize={11} fill={C.inkSoft}>FIFO</text> : <g />} />
                <Line type="monotone" dataKey="avg_share_pr" name="Pro-rata" stroke={C.oxblood} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: C.paper2, fill: C.oxblood }} animationDuration={900}
                  label={(p: { x: number; y: number; index: number; value: number }) => p.index === layerData.length - 1 ? <text x={p.x + 8} y={p.y + 4} fontSize={11} fill={C.inkSoft}>Pro-rata</text> : <g />} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="tiny mute2">The further money travels, the more it mixes with other funds — and the more the conventions disagree (shaded gap).</p>
        </Card>
        <Card title="Synthetic scenarios" sub="Ground-truth labels from the generator (display only)">
          <HBars data={[...data.scenario_breakdown].sort((a, b) => b.n - a.n).map((d) => ({ key: d.scenario, label: scenarioLabel(d.scenario), value: d.n, color: SCENARIO_COLOR[d.scenario] ?? C.clay }))} />
        </Card>
      </motion.div>

      <motion.div className="grid g4 mt" variants={staggerParent}>
        {data.layer_profile.slice(0, 4).map((l) => (
          <Card key={l.layer}>
            <div className="stat">
              <span className="label">Layer {l.layer} · {int(l.n_accounts)} accounts</span>
              {([['Pro-rata', l.avg_share_pr, C.oxblood], ['FIFO', l.avg_share_fifo, C.saffron]] as const).map(([name, v, col], i) => (
                <div key={name} className="row" style={{ gap: 8 }}>
                  <span className="tiny mute2" style={{ width: 52 }}>{name}</span>
                  <div className="rangebar" style={{ flex: 1, height: 8 }}>
                    <motion.div className="fill" style={{ left: 0, background: col }} initial={{ width: 0 }} animate={{ width: `${v * 100}%` }} transition={{ duration: 0.9, delay: 0.1 * i + 0.2 }} />
                  </div>
                </div>
              ))}
              <span className="sub">traceable share {pct(l.avg_share_pr, 0)} (PR) – {pct(l.avg_share_fifo, 0)} (FIFO)</span>
            </div>
          </Card>
        ))}
      </motion.div>
    </motion.div>
  );
}
