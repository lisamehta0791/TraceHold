import { api } from '../api';
import { Card } from '../components/Card';
import { ErrorCard } from '../components/ErrorCard';
import { RowsSkeleton } from '../components/Skeleton';
import { int } from '../lib/format';
import { useAsync } from '../lib/useAsync';

const mb = (b: number | null | undefined) => (b == null ? '—' : `${(Number(b) / 1048576).toLocaleString('en-IN', { maximumFractionDigits: 1 })} MB`);

/** What Exasol did in the latest run, read from its own system tables. */
export function ExasolFacts() {
  const { data, error, reload } = useAsync(() => api.exasol(), []);
  if (error) return <ErrorCard error={error} onRetry={reload} />;
  if (!data) return <RowsSkeleton rows={2} />;
  const r = data.last_run;
  const tx = data.source_tables.find((t) => t.name === 'TRANSACTIONS');
  return (
    <Card title={r ? `Inside Exasol during analysis run #${r.run_id}` : 'Inside Exasol'} sub={`Read from Exasol's own system tables · Exasol ${data.version}`}>
      <div className="basis-facts">
        {r && <div><b>{int(r.statements)}</b><span>SQL statements executed</span></div>}
        {r && <div><b>{int(r.rows)}</b><span>rows written or returned</span></div>}
        <div><b>{data.indexes.total} / {data.indexes.created_by_tracehold}</b><span>indexes Exasol built by itself / written by hand</span></div>
        {tx && <div><b>{(Number(tx.raw) / Math.max(1, Number(tx.mem))).toFixed(1)}× smaller</b><span>transactions in memory: {mb(tx.raw)} raw → {mb(tx.mem)}</span></div>}
      </div>
    </Card>
  );
}
