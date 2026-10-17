import { motion } from 'motion/react';
import type { CSSProperties, ReactNode } from 'react';
import type { Classification, RequestStatus, Status } from '../types';
import { CLASS_COLOR, CLASS_LABEL, REQ_COLOR, REQ_LABEL, scenarioLabel, STATUS_COLOR, STATUS_LABEL } from '../lib/format';

const cvar = (c: string) => ({ '--c': c } as CSSProperties);

export function Chip({ color, children, title }: { color: string; children: ReactNode; title?: string }) {
  return (
    <span className="chip tint" style={cvar(color)} title={title}>
      <span className="dot" />
      {children}
    </span>
  );
}

export function StatusChip({ status, title }: { status: Status; title?: string }) {
  if (status === 'OUT_OF_SCOPE') return <span className="chip dashed" title={title}>{STATUS_LABEL[status]}</span>;
  if (status === 'UNDETERMINABLE') return <span className="chip hatch" title={title}>{STATUS_LABEL[status]}</span>;
  return <Chip color={STATUS_COLOR[status]} title={title}>{STATUS_LABEL[status]}</Chip>;
}

export function ClassChip({ c }: { c: Classification | null | undefined }) {
  if (!c) return <span className="chip plain">Not requested</span>;
  if (c === 'CANNOT_DETERMINE') return <span className="chip hatch">{CLASS_LABEL[c]}</span>;
  return <Chip color={CLASS_COLOR[c]}>{CLASS_LABEL[c]}</Chip>;
}

export function ReqChip({ s }: { s: RequestStatus }) {
  return <Chip color={REQ_COLOR[s]}>{REQ_LABEL[s]}</Chip>;
}

export function ScenarioChip({ s, label = true }: { s: string; label?: boolean }) {
  return (
    <span className="chip syn" title="Ground-truth scenario label from the synthetic data generator (display only)">
      {scenarioLabel(s)}
      {label && <span className="mute2" style={{ fontWeight: 400 }}>· synthetic scenario</span>}
    </span>
  );
}

export function isLight(hex: string) {
  const h = hex.replace('#', '');
  if (h.length !== 6) return false;
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return 0.299 * r + 0.587 * g + 0.114 * b > 150;
}

/** Toggle chip with a spring-animated fill. */
export function ToggleChip({ on, onClick, children, count, color }: { on: boolean; onClick: () => void; children: ReactNode; count?: number; color?: string }) {
  const c = color ?? '#7A2232';
  return (
    <motion.button
      type="button"
      className={`togglechip ${on ? 'on' : ''}`}
      onClick={onClick}
      whileTap={{ scale: 0.93 }}
      whileHover={{ y: -1 }}
      style={{ ...cvar(c), color: on ? (isLight(c) ? 'var(--ink)' : '#FBEFE2') : undefined }}
      aria-pressed={on}
    >
      {on && (
        <motion.span className="chip-bg" initial={{ scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: 'spring', stiffness: 500, damping: 26 }} />
      )}
      {children}
      {count !== undefined && <span className="count">{count.toLocaleString('en-IN')}</span>}
    </motion.button>
  );
}
