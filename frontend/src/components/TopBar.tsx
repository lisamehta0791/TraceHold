import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { api } from '../api';
import type { Health } from '../types';
import { IconDb } from './Icons';

const TITLES: [RegExp, string][] = [
  [/^\/analyze/, 'Live analysis'],
  [/^\/cases\/.+/, 'Cases · one case'],
  [/^\/cases/, 'Cases'],
  [/^\/lien-review/, 'Lien review'],
  [/^\/system/, 'System'],
  [/^\/ask/, 'Ask the results'],
];

function compactCount(n: number) {
  if (n >= 1e6) return `${(n / 1e6).toFixed(2).replace(/0$/, '')}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return String(n);
}

export function TopBar() {
  const { pathname } = useLocation();
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () => api.health().then((h) => { if (alive) { setHealth(h); setErr(false); } }).catch(() => alive && setErr(true));
    load();
    const t = setInterval(load, 30000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const title = TITLES.find(([re]) => re.test(pathname))?.[1] ?? 'TraceHold';
  const ok = health && health.db === 'ok';
  return (
    <header className="topbar">
      <span className="crumb">{title}</span>
      <span className="grow" />
      <span className="synthetic-tag" title="Every account, case and transaction in TraceHold is generated synthetically">Synthetic data</span>
      <span className={`health ${err || (health && !ok) ? 'bad' : !health ? 'wait' : ''}`} title={health ? `Exasol ${health.exasol_version} · schema ${health.schema} · run #${health.latest_run_id ?? '—'}` : undefined}>
        <span className="dot" />
        <IconDb size={14} />
        {err ? 'Database unreachable' : !health ? 'Checking database…' : ok
          ? <>Exasol connected · <span className="num">{compactCount(health.row_counts.transactions)}</span> transactions</>
          : `Exasol: ${health.db}`}
      </span>
    </header>
  );
}
