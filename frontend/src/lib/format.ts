import type { Classification, Convention, RequestStatus, Scenario, Status } from '../types';

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const inr0 = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
const num = new Intl.NumberFormat('en-IN');

/** ₹1,00,000.00 */
export const rupees = (x: number | null | undefined) => (x === null || x === undefined || Number.isNaN(x) ? '—' : inr.format(x));
/** ₹1,00,000 */
export const rupees0 = (x: number | null | undefined) => (x === null || x === undefined || Number.isNaN(x) ? '—' : inr0.format(x));

/** Compact lakh / crore: ₹6.7 L, ₹45.2 Cr, ₹8,500 */
export function rupeesCompact(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const sign = x < 0 ? '−' : '';
  const a = Math.abs(x);
  if (a >= 1e7) return `${sign}₹${trim((a / 1e7).toFixed(digits))} Cr`;
  if (a >= 1e5) return `${sign}₹${trim((a / 1e5).toFixed(digits))} L`;
  if (a >= 1e3) return `${sign}₹${num.format(Math.round(a))}`;
  return `${sign}₹${trim(a.toFixed(a < 10 && a > 0 ? 2 : 0))}`;
}
/** Axis-friendly compact without currency symbol clutter */
export function compactNum(x: number): string {
  const a = Math.abs(x);
  if (a >= 1e7) return `${trim((x / 1e7).toFixed(1))} Cr`;
  if (a >= 1e5) return `${trim((x / 1e5).toFixed(1))} L`;
  if (a >= 1e3) return `${trim((x / 1e3).toFixed(1))}K`;
  return `${trim(x.toFixed(0))}`;
}
const trim = (s: string) => s.replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');

export const int = (x: number | null | undefined) => (x === null || x === undefined ? '—' : num.format(Math.round(x)));
export const pct = (x: number | null | undefined, digits = 1) =>
  x === null || x === undefined || Number.isNaN(x) ? '—' : `${(x * 100).toFixed(digits)}%`;
export const ratio = (x: number | null | undefined) => (x === null || x === undefined ? '—' : `${x.toFixed(2)}×`);

export function dateTime(ts: string | null | undefined): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}
export function timeOnly(ts: string | null | undefined): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
}
export function dateOnly(ts: string | null | undefined): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export const humanize = (s: string | null | undefined) => (s ?? '').toLowerCase().replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

export const STATUS_LABEL: Record<Status, string> = {
  DETERMINED: 'Determined', RANGE: 'Range', UNDETERMINABLE: 'Undeterminable', OUT_OF_SCOPE: 'Out of observable scope',
};
export const CLASS_LABEL: Record<Classification, string> = {
  WITHIN_EVIDENCE: 'Within evidence', WITHIN_RANGE: 'Within range', EXCEEDS_EVIDENCE: 'Exceeds evidence', CANNOT_DETERMINE: 'Cannot determine',
};
export const REQ_LABEL: Record<RequestStatus, string> = { COMPLETE: 'Complete', INCOMPLETE: 'Incomplete', CONFLICTING: 'Conflicting' };
export const CONV_LABEL: Record<Convention, string> = { PR: 'Pro-rata', FIFO: 'FIFO', LIFO: 'LIFO (bound)' };
export const scenarioLabel = (s: Scenario | string) => humanize(s);

// Palette tokens (mirrors theme.css) for SVG / canvas / three.js use.
export const C = {
  paper: '#F4ECDF', paper2: '#EADFCB', paper3: '#E0D0B5', ink: '#2A1B14', inkSoft: '#5B4636',
  oxblood: '#7A2232', terracotta: '#C2553A', saffron: '#E39B2D', olive: '#6E7B3A', clay: '#B98B6A', rose: '#D98C7A', sand: '#CDB48A',
};
export const CONV_COLOR: Record<Convention, string> = { PR: C.oxblood, FIFO: C.saffron, LIFO: C.olive };
export const CLASS_COLOR: Record<Classification, string> = {
  WITHIN_EVIDENCE: C.olive, WITHIN_RANGE: C.saffron, EXCEEDS_EVIDENCE: C.terracotta, CANNOT_DETERMINE: C.clay,
};
export const STATUS_COLOR: Record<Status, string> = { DETERMINED: C.olive, RANGE: C.saffron, UNDETERMINABLE: C.clay, OUT_OF_SCOPE: C.inkSoft };
export const REQ_COLOR: Record<RequestStatus, string> = { COMPLETE: C.olive, INCOMPLETE: C.saffron, CONFLICTING: C.terracotta };
/** Fixed categorical order for scenarios (assigned by entity, never by rank). */
export const SCENARIO_COLOR: Record<string, string> = {
  ALL: C.ink, SIMPLE_CHAIN: C.oxblood, SPLIT_MERGE: C.saffron, COMMINGLED: C.olive, INNOCENT_RECIPIENT: C.rose,
  BUSINESS_TURNOVER: C.inkSoft, RAPID_CASHOUT: C.terracotta, CROSS_INSTITUTION: C.clay, REVERSAL_FAILED: C.sand,
  SHARED_ACCOUNT: '#8E5B3E', WORKED_EXAMPLE: '#A3463A',
};

/** Run step names carry internal feature codes ("CF3 sizing, CF6 status"); show them in plain words. */
export const plainStep = (name: string) =>
  name.replace(/\b(?:CF|AF)\d(?:\/(?:CF|AF)\d)*\s*/g, '').replace(/^./, (c) => c.toUpperCase());
