import { motion } from 'motion/react';
import { C, CONV_COLOR, rupees } from '../lib/format';
import type { Convention } from '../types';
import { useMotionOK } from '../lib/motion';

interface RangeBarProps {
  lower: number;
  upper: number;
  requested?: number | null;
  lowerExt?: number;
  upperExt?: number;
  markers?: Partial<Record<Convention, number>>;
  /** scale maximum; defaults to max of all values */
  max?: number;
  height?: number;
  showLegend?: boolean;
  compact?: boolean;
}

/**
 * Supported range bar: solid olive to the lower bound (supported under every convention),
 * saffron band between lower and upper (convention-dependent), faint band for the LIFO bounding
 * case, terracotta hatched overflow where a request exceeds the upper bound.
 */
export function RangeBar({ lower, upper, requested, lowerExt, upperExt, markers, max, height = 10, showLegend, compact }: RangeBarProps) {
  const motionOK = useMotionOK();
  const vals = [upper, requested ?? 0, upperExt ?? 0, ...Object.values(markers ?? {})];
  const M = Math.max(1, max ?? Math.max(...vals) * 1.04);
  const p = (x: number) => `${Math.max(0, Math.min(100, (x / M) * 100))}%`;
  const t = (delay = 0) => (motionOK ? { duration: 0.9, delay, ease: [0.2, 0.8, 0.2, 1] as const } : { duration: 0 });
  const over = requested !== null && requested !== undefined && requested > upper + 0.5;
  const title = `Supported ${rupees(lower)} – ${rupees(upper)}${requested != null ? ` · requested ${rupees(requested)}` : ''}`;
  return (
    <div style={{ width: '100%' }}>
      <div className="rangebar" style={{ height, marginTop: compact ? 3 : 8, marginBottom: compact ? 3 : 8 }} title={title}>
        {upperExt !== undefined && lowerExt !== undefined && (
          <motion.div className="fill" style={{ left: p(lowerExt), background: 'rgba(110,123,58,0.18)', border: '1px dashed rgba(110,123,58,0.6)' }}
            initial={{ width: 0 }} animate={{ width: `calc(${p(upperExt)} - ${p(lowerExt)})` }} transition={t(0.1)} />
        )}
        {over && (
          <motion.div className="fill" style={{ left: p(upper), backgroundImage: 'repeating-linear-gradient(45deg, rgba(194,85,58,0.55) 0 3px, rgba(194,85,58,0.15) 3px 7px)' }}
            initial={{ width: 0 }} animate={{ width: `calc(${p(requested!)} - ${p(upper)})` }} transition={t(0.35)} />
        )}
        <motion.div className="fill" style={{ left: p(lower), background: C.saffron }}
          initial={{ width: 0 }} animate={{ width: `calc(${p(upper)} - ${p(lower)})` }} transition={t(0.15)} />
        <motion.div className="fill" style={{ left: 0, background: C.olive }} initial={{ width: 0 }} animate={{ width: p(lower) }} transition={t(0)} />
        {markers && (Object.entries(markers) as [Convention, number][]).map(([c, v]) => (
          <motion.div key={c} className="marker" style={{ background: CONV_COLOR[c], boxShadow: '0 0 0 2px var(--paper-2)' }}
            initial={{ left: '0%', opacity: 0 }} animate={{ left: p(v), opacity: 1 }} transition={t(0.25)} title={`${c}: ${rupees(v)}`} />
        ))}
        {requested !== null && requested !== undefined && (
          <motion.div className="req" style={{ borderTopColor: over ? C.terracotta : C.ink }} initial={{ left: '0%', opacity: 0 }} animate={{ left: p(requested), opacity: 1 }} transition={t(0.4)} title={`Requested ${rupees(requested)}`} />
        )}
      </div>
      {showLegend && (
        <div className="row wrap tiny muted" style={{ gap: 12, marginTop: 6 }}>
          <span className="row gap-s"><i style={{ width: 12, height: 8, background: C.olive, borderRadius: 3, display: 'inline-block' }} />Supported under all conventions</span>
          <span className="row gap-s"><i style={{ width: 12, height: 8, background: C.saffron, borderRadius: 3, display: 'inline-block' }} />Convention-dependent</span>
          {upperExt !== undefined && <span className="row gap-s"><i style={{ width: 12, height: 8, border: '1px dashed rgba(110,123,58,0.8)', borderRadius: 3, display: 'inline-block' }} />LIFO bounding</span>}
          {markers && (Object.keys(markers) as Convention[]).map((c) => (
            <span key={c} className="row gap-s"><i style={{ width: 2, height: 12, background: CONV_COLOR[c], display: 'inline-block' }} />{c === 'PR' ? 'Pro-rata' : c}</span>
          ))}
          {requested != null && <span className="row gap-s"><i style={{ width: 0, height: 0, borderLeft: '5px solid transparent', borderRight: '5px solid transparent', borderTop: `7px solid ${over ? C.terracotta : C.ink}`, display: 'inline-block' }} />Requested</span>}
        </div>
      )}
    </div>
  );
}
