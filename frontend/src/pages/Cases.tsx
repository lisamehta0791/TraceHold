import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import type { CaseQuery, Classification, RequestStatus, Scenario } from '../types';
import { Button } from '../components/Button';
import { ClassChip, ReqChip, ScenarioChip, ToggleChip } from '../components/Chip';
import { ErrorCard } from '../components/ErrorCard';
import { IconChevron, IconChevronLeft, IconSearch } from '../components/Icons';
import { PageHead } from '../components/Page';
import { Tabs } from '../components/Tabs';
import Dashboard from './Dashboard';
import { RangeBar } from '../components/RangeBar';
import { RowsSkeleton } from '../components/Skeleton';
import { CLASS_COLOR, CLASS_LABEL, REQ_COLOR, REQ_LABEL, SCENARIO_COLOR, dateTime, int, rupeesCompact, scenarioLabel } from '../lib/format';
import { useAsync } from '../lib/useAsync';

const SCENARIOS: Scenario[] = ['SIMPLE_CHAIN', 'SPLIT_MERGE', 'COMMINGLED', 'INNOCENT_RECIPIENT', 'BUSINESS_TURNOVER', 'RAPID_CASHOUT', 'CROSS_INSTITUTION', 'REVERSAL_FAILED', 'SHARED_ACCOUNT', 'WORKED_EXAMPLE'];
const CLASSES: Classification[] = ['WITHIN_EVIDENCE', 'WITHIN_RANGE', 'EXCEEDS_EVIDENCE', 'CANNOT_DETERMINE'];
const REQS: RequestStatus[] = ['COMPLETE', 'INCOMPLETE', 'CONFLICTING'];
const PAGE_SIZE = 25;

export default function Cases() {
  const [tab, setTab] = useState('list');
  return (
    <div>
      <PageHead eyebrow="Cases · stored in Exasol" title="Cases"
        lede="The 2,400 synthetic fraud cases that were analysed in Exasol. Open any case to see its money trail and how every figure was calculated." />
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'list', label: 'All cases' }, { key: 'glance', label: 'At a glance' }]} />
      <div style={{ paddingTop: 18 }}>{tab === 'list' ? <CaseList /> : <Dashboard embedded />}</div>
    </div>
  );
}

function CaseList() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const q: CaseQuery = {
    search: sp.get('search') ?? undefined,
    scenario: sp.get('scenario') ?? undefined,
    classification: sp.get('classification') ?? undefined,
    request_status: sp.get('request_status') ?? undefined,
    sort: (sp.get('sort') as CaseQuery['sort']) ?? 'fraud_ts',
    page: Number(sp.get('page') ?? 1),
    page_size: PAGE_SIZE,
  };
  const [search, setSearch] = useState(q.search ?? '');
  const set = (patch: Record<string, string | undefined>) => {
    const next = new URLSearchParams(sp);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!('page' in patch)) next.delete('page');
    setSp(next, { replace: true });
  };
  useEffect(() => {
    const t = setTimeout(() => { if ((q.search ?? '') !== search) set({ search: search || undefined }); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const key = sp.toString();
  const { data, error, loading, reload } = useAsync(() => api.cases(q), [key]);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const maxVal = data ? Math.max(1, ...data.items.map((i) => Math.max(i.requested_total, i.supported_upper))) : 1;

  return (
    <div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row wrap" style={{ gap: 14, justifyContent: 'space-between' }}>
          <div className="search">
            <IconSearch size={16} />
            <input className="input" placeholder="Search case ID, reference or account…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search cases" />
          </div>
          <label className="row small muted" style={{ gap: 8 }}>
            Sort by
            <select className="input" value={q.sort} onChange={(e) => set({ sort: e.target.value })}>
              <option value="fraud_ts">Most recent fraud</option>
              <option value="loss">Largest loss</option>
              <option value="overbroad">Most over-broad request</option>
            </select>
          </label>
        </div>
        <div className="stack mt" style={{ gap: 10 }}>
          <FilterRow label="Classification">
            {CLASSES.map((c) => (
              <ToggleChip key={c} on={q.classification === c} color={CLASS_COLOR[c]} onClick={() => set({ classification: q.classification === c ? undefined : c })}>{CLASS_LABEL[c]}</ToggleChip>
            ))}
          </FilterRow>
          <FilterRow label="Request">
            {REQS.map((c) => (
              <ToggleChip key={c} on={q.request_status === c} color={REQ_COLOR[c]} onClick={() => set({ request_status: q.request_status === c ? undefined : c })}>{REQ_LABEL[c]}</ToggleChip>
            ))}
          </FilterRow>
          <FilterRow label="Scenario">
            {SCENARIOS.map((c) => (
              <ToggleChip key={c} on={q.scenario === c} color={SCENARIO_COLOR[c]} onClick={() => set({ scenario: q.scenario === c ? undefined : c })}>{scenarioLabel(c)}</ToggleChip>
            ))}
          </FilterRow>
        </div>
      </div>

      {error ? (
        <ErrorCard error={error} onRetry={reload} />
      ) : !data ? (
        <div className="card"><RowsSkeleton rows={10} /></div>
      ) : (
        <div className="card" style={{ padding: 0, opacity: loading ? 0.6 : 1, transition: 'opacity .2s' }}>
          <div className="table-wrap">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Case</th><th>Scenario</th><th>Fraud time</th><th className="r">Loss</th><th>Request</th>
                  <th style={{ minWidth: 220 }}>Supported vs requested</th><th>Worst</th><th className="r">Accts</th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence initial={true} mode="popLayout">
                  {data.items.map((c, i) => (
                    <motion.tr
                      key={c.case_id}
                      className="clickable"
                      onClick={() => nav(`/cases/${c.case_id}`)}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0, transition: { delay: i * 0.018, duration: 0.3 } }}
                      exit={{ opacity: 0 }}
                    >
                      <td>
                        <div className="mono small" style={{ fontWeight: 600 }}>{c.case_ref}</div>
                        <div className="tiny mute2">#{c.case_id}</div>
                      </td>
                      <td><ScenarioChip s={c.scenario} label={false} /></td>
                      <td className="small muted">{dateTime(c.fraud_ts)}</td>
                      <td className="r num">{rupeesCompact(c.reported_loss)}</td>
                      <td><ReqChip s={c.request_status} /></td>
                      <td>
                        <RangeBar compact lower={c.supported_lower} upper={c.supported_upper} requested={c.requested_total} max={maxVal} height={8} />
                        <div className="tiny mute2 num">{rupeesCompact(c.supported_lower)}–{rupeesCompact(c.supported_upper)} vs {rupeesCompact(c.requested_total)}</div>
                      </td>
                      <td><ClassChip c={c.worst_classification} /></td>
                      <td className="r num">{c.n_accounts}{c.n_out_of_scope > 0 && <span className="mute2 tiny"> +{c.n_out_of_scope} oos</span>}</td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
            {data.items.length === 0 && <p className="muted" style={{ padding: 24, textAlign: 'center' }}>No cases match these filters.</p>}
          </div>
          <div className="row between" style={{ padding: '12px 16px', borderTop: '1px solid var(--paper-3)' }}>
            <span className="small muted">{int(data.total)} cases · page {data.page} of {pages}</span>
            <div className="row">
              <Button size="sm" icon={<IconChevronLeft size={15} />} disabled={data.page <= 1} onClick={() => set({ page: String(data.page - 1) })}>Previous</Button>
              <Button size="sm" disabled={data.page >= pages} onClick={() => set({ page: String(data.page + 1) })}>Next <IconChevron size={15} /></Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="row" style={{ alignItems: 'flex-start', gap: 12 }}>
      <span className="eyebrow" style={{ width: 118, paddingTop: 8, flex: '0 0 auto' }}>{label}</span>
      <div className="chiprow">{children}</div>
    </div>
  );
}
