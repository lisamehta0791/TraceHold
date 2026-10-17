// Shared recharts styling: recessive hairline grid, palette marks, paper tooltip.
import type { ReactNode } from 'react';
import { C } from '../lib/format';

export const axisProps = {
  stroke: C.paper3,
  tick: { fill: C.inkSoft, fontSize: 11.5, fontFamily: 'DM Sans Variable, DM Sans, sans-serif' },
  tickLine: false,
  axisLine: { stroke: C.paper3 },
};
export const gridProps = { stroke: 'rgba(91,70,54,0.12)', strokeDasharray: undefined, vertical: false };
export const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];
export const BAR_RADIUS_H: [number, number, number, number] = [0, 4, 4, 0];

interface TipPayload { name?: string; value?: number | string; color?: string; dataKey?: string | number; payload?: Record<string, unknown> }
interface TipProps {
  active?: boolean;
  payload?: TipPayload[];
  label?: string | number;
  fmt?: (v: number, name?: string) => string;
  labelFmt?: (l: string | number) => ReactNode;
}

/** Paper-2 tooltip; value leads, series name follows, line keys. */
export function ChartTip({ active, payload, label, fmt = (v) => v.toLocaleString('en-IN'), labelFmt }: TipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tip">
      {label !== undefined && <div className="tip-title">{labelFmt ? labelFmt(label) : label}</div>}
      {payload.map((p, i) => (
        <div className="tip-row" key={i}>
          <span className="v">{typeof p.value === 'number' ? fmt(p.value, p.name) : p.value}</span>
          <span className="k">
            <i className="key" style={{ background: p.color }} />
            {p.name}
          </span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; kind?: 'rect' | 'line' | 'hatch' }[] }) {
  return (
    <div className="row wrap" style={{ gap: 14, fontSize: 12, color: C.inkSoft }}>
      {items.map((it) => (
        <span key={it.label} className="row gap-s">
          <i
            style={{
              display: 'inline-block',
              width: it.kind === 'line' ? 14 : 11,
              height: it.kind === 'line' ? 3 : 11,
              borderRadius: it.kind === 'line' ? 2 : 3,
              background: it.color,
              backgroundImage: it.kind === 'hatch' ? 'repeating-linear-gradient(45deg, rgba(42,27,20,0.35) 0 2px, transparent 2px 5px)' : undefined,
            }}
          />
          {it.label}
        </span>
      ))}
    </div>
  );
}

/** SVG pattern defs for hatched fills (CANNOT_DETERMINE etc.). Place inside a recharts chart. */
export function HatchDefs({ id = 'hatch', color = C.clay }: { id?: string; color?: string }) {
  return (
    <defs>
      <pattern id={id} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill={color} opacity="0.55" />
        <line x1="0" y1="0" x2="0" y2="6" stroke={C.ink} strokeOpacity="0.35" strokeWidth="2" />
      </pattern>
    </defs>
  );
}

/** Non-wrapping value label above a bar (recharts `label` prop render function). */
export function topLabel(fmt: (v: number) => string) {
  // eslint-disable-next-line react/display-name
  return (p: { x?: number | string; y?: number | string; width?: number | string; value?: number | string }) => {
    const x = Number(p.x ?? 0) + Number(p.width ?? 0) / 2;
    const y = Number(p.y ?? 0) - 6;
    return (
      <text x={x} y={y} textAnchor="middle" fontSize={10.5} fill={C.inkSoft} fontFamily="JetBrains Mono Variable, monospace">
        {typeof p.value === 'number' ? fmt(p.value) : p.value}
      </text>
    );
  };
}
