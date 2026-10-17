import { motion } from 'motion/react';
import { useState } from 'react';
import { useMotionOK } from '../lib/motion';

export interface HBarDatum { key: string; label: string; value: number; color: string; hatch?: boolean; dashed?: boolean; note?: string }

/** Animated horizontal bars with value at the tip; hover lifts the bar and shows a note. */
export function HBars({ data, format = (v) => v.toLocaleString('en-IN'), max, showShare }: { data: HBarDatum[]; format?: (v: number) => string; max?: number; showShare?: boolean }) {
  const motionOK = useMotionOK();
  const [hover, setHover] = useState<string | null>(null);
  const M = Math.max(1, max ?? Math.max(...data.map((d) => d.value)));
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  return (
    <div className="stack" style={{ gap: 9 }} role="list">
      {data.map((d, i) => (
        <div
          key={d.key}
          role="listitem"
          onMouseEnter={() => setHover(d.key)}
          onMouseLeave={() => setHover(null)}
          tabIndex={0}
          onFocus={() => setHover(d.key)}
          onBlur={() => setHover(null)}
          style={{ display: 'grid', gridTemplateColumns: 'minmax(110px, 34%) 1fr', gap: 12, alignItems: 'center', outline: 'none' }}
          title={d.note}
        >
          <span className="small" style={{ color: hover === d.key ? 'var(--ink)' : 'var(--ink-soft)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.label}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <div style={{ flex: 1, position: 'relative', height: 16 }}>
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${(d.value / M) * 100}%`, filter: hover === d.key ? 'brightness(1.08)' : 'brightness(1)' }}
                transition={motionOK ? { duration: 0.8, delay: 0.05 * i, ease: [0.2, 0.8, 0.2, 1] } : { duration: 0 }}
                style={{
                  height: '100%', borderRadius: '0 4px 4px 0', minWidth: d.value > 0 ? 3 : 0,
                  background: d.dashed ? 'transparent' : d.color,
                  border: d.dashed ? `1.5px dashed ${d.color}` : undefined,
                  backgroundImage: d.hatch ? 'repeating-linear-gradient(45deg, rgba(42,27,20,0.28) 0 2px, transparent 2px 6px)' : undefined,
                  boxShadow: hover === d.key ? '0 2px 8px rgba(42,27,20,0.18)' : undefined,
                }}
              />
            </div>
            <span className="num small" style={{ minWidth: 64, textAlign: 'right' }}>
              {format(d.value)}
              {showShare && <span className="mute2 tiny"> · {((d.value / total) * 100).toFixed(0)}%</span>}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
