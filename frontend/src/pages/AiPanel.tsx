import { api } from '../api';
import { Card } from '../components/Card';
import { ErrorCard } from '../components/ErrorCard';
import { IconAlert, IconCheck, IconShield } from '../components/Icons';
import { RowsSkeleton } from '../components/Skeleton';
import { dateTime, pct } from '../lib/format';
import { useAsync } from '../lib/useAsync';

const BOUNDARY: [string, string, string][] = [
  ['Reading free-text police letters (CF9)', 'Yes, optional', 'Every value must quote the letter, is checked by fixed rules and is confirmed by a person.'],
  ['Money trail (CF2)', 'No', 'Set-based SQL in Exasol.'],
  ['Sizing, allocation and layer analysis (CF3, CF4)', 'No', 'SQL with a conservation check.'],
  ['Request checks, statuses, abstention (CF1, CF5, CF6)', 'No', 'Rules, reproducible.'],
  ['Figures in the evidence packet (CF7)', 'No', 'Every figure resolves to transaction records.'],
  ['Questions over the results (AF7)', 'Yes, optional', 'Read-only views through Exasol’s MCP server; the SQL and rows are shown; numbers are checked.'],
  ['Wording of the account-holder letter (AF8)', 'Yes, optional', 'The AI may only reword; a check confirms every fact, otherwise the template is kept.'],
  ['Detecting or scoring accounts', 'Not done', 'Out of scope by design.'],
];

type Ev = {
  available: boolean; generated_at?: string; model?: string; note?: string;
  cf9?: { letters: number; fields: { field: string; tp: number; fp: number; fn: number; precision: number | null; recall: number | null }[];
    overall: { precision: number; recall: number; exact_match_letters: number; values_without_quote: number; needs_correction_share: number };
    conflicts: { planted: number; flagged: number } };
  af7?: { questions: number; correct: number; share_correct: number; fidelity_failures: number; items: { question: string; ok: boolean; note: string }[] };
  af8?: { letters: number; used_ai: number; fell_back: number; fidelity_share: number; fallback_share: number };
  ai_off?: { passed: boolean; detail: string };
};

export function AiPanel() {
  const st = useAsync(() => api.aiStatus(), []);
  const ev = useAsync(() => api.aiEvaluation() as Promise<Ev>, []);
  const log = useAsync(() => api.aiLog(25), []);
  const s = st.data;
  const e = ev.data;
  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="note ox"><IconShield size={16} /><span><b>No model produces or changes a figure.</b> Every number comes from SQL in Exasol and passes the
        conservation check. AI only reads letters, answers questions over results and rewords a finished letter, and the app works fully with AI switched off.</span></div>

      <div className="grid g2" style={{ alignItems: 'start' }}>
        <Card title="Where AI is used, and where it is not">
          <table className="ledger">
            <thead><tr><th>Area</th><th>AI?</th><th>Why</th></tr></thead>
            <tbody>{BOUNDARY.map(([a, u, w]) => (
              <tr key={a}><td className="small"><b>{a}</b></td><td className="small" style={{ whiteSpace: 'nowrap', color: u.startsWith('Yes') ? 'var(--saffron-deep, #B5781F)' : 'var(--olive)' }}>{u}</td><td className="small muted">{w}</td></tr>
            ))}</tbody>
          </table>
        </Card>
        <Card title="Set-up">
          {st.error ? <ErrorCard error={st.error} /> : !s ? <RowsSkeleton rows={4} /> : (
            <ul className="clean stack small" style={{ gap: 8 }}>
              <li>· Model: <b>{s.llm.model}</b> on {s.llm.provider}, temperature {s.llm.temperature}, seed {s.llm.seed}: {s.llm.enabled ? <b style={{ color: 'var(--olive)' }}>on</b> : <b style={{ color: 'var(--terracotta)' }}>off ({s.llm.reason})</b>}</li>
              <li>· Questions run through Exasol's open-source MCP server <b>{s.mcp.package}</b> (installed in the project) as read-only user <b>{s.mcp.user}</b> {s.reader_ready ? '' : '(not set up: run python -m app.ai_setup)'}</li>
              <li>· Only synthetic data is sent to the model; every call is logged in Exasol (table AI_LOG).</li>
              {s.counts && <li>· So far: {s.counts.letters} synthetic letters, {s.counts.extractions} letter readings, {s.counts.confirmations} confirmed fields, {s.counts.questions} questions, {s.counts.ai_calls} AI calls.</li>}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Measured results (held-out synthetic letters and fixed question sets)" sub={e?.generated_at ? `Generated ${dateTime(e.generated_at)} with ${e.model}` : undefined}>
        {ev.error ? <ErrorCard error={ev.error} /> : !e ? <RowsSkeleton rows={4} /> : !e.available ? (
          <p className="muted small">Not measured yet. Run <code>python -m app.ai_eval</code> from the backend folder.</p>
        ) : (
          <div className="stack" style={{ gap: 16 }}>
            {e.ai_off && <div className={`note ${e.ai_off.passed ? 'olive' : ''}`}>{e.ai_off.passed ? <IconCheck size={15} /> : <IconAlert size={15} />}<span><b>AI-off test {e.ai_off.passed ? 'passed' : 'failed'}:</b> {e.ai_off.detail}</span></div>}
            {e.cf9 && (
              <div>
                <h3 style={{ marginBottom: 6 }}>Reading letters (CF9): {e.cf9.letters} held-out letters</h3>
                <div className="basis-facts" style={{ marginBottom: 10 }}>
                  <div><b>{pct(e.cf9.overall.precision)}</b><span>precision (values used that were right)</span></div>
                  <div><b>{pct(e.cf9.overall.recall)}</b><span>recall (stated values that were found)</span></div>
                  <div><b>{pct(e.cf9.overall.exact_match_letters)}</b><span>letters with every field right</span></div>
                  <div><b>{e.cf9.overall.values_without_quote}</b><span>values used without a quote from the letter (must be 0)</span></div>
                  <div><b>{pct(e.cf9.overall.needs_correction_share)}</b><span>fields a person would have to correct</span></div>
                  <div><b>{e.cf9.conflicts.flagged} / {e.cf9.conflicts.planted}</b><span>planted conflicting amounts flagged</span></div>
                </div>
                <table className="ledger">
                  <thead><tr><th>Field</th><th className="r">Right</th><th className="r">Wrong / invented</th><th className="r">Missed</th><th className="r">Precision</th><th className="r">Recall</th></tr></thead>
                  <tbody>{e.cf9.fields.map((f) => (
                    <tr key={f.field}><td className="small">{f.field.replace(/_/g, ' ')}</td><td className="r num">{f.tp}</td><td className="r num">{f.fp}</td><td className="r num">{f.fn}</td>
                      <td className="r num">{f.precision == null ? '—' : pct(f.precision)}</td><td className="r num">{f.recall == null ? '—' : pct(f.recall)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            {e.af7 && (
              <div>
                <h3 style={{ marginBottom: 6 }}>Questions (AF7): {e.af7.correct} of {e.af7.questions} answered with the same rows as hand-written SQL · {e.af7.fidelity_failures} wordings rejected by the number check</h3>
                <ul className="clean stack small" style={{ gap: 4 }}>{e.af7.items.map((it) => (
                  <li key={it.question} className="row" style={{ gap: 6 }}>{it.ok ? <IconCheck size={12} /> : <IconAlert size={12} />} {it.question} <span className="muted">{it.note}</span></li>
                ))}</ul>
              </div>
            )}
            {e.af8 && (
              <div>
                <h3 style={{ marginBottom: 6 }}>Rewording (AF8): {e.af8.letters} letters</h3>
                <p className="small">{pct(e.af8.fidelity_share)} kept every fact and were used; {pct(e.af8.fallback_share)} failed the check and fell back to the template.</p>
              </div>
            )}
            {e.note && <p className="tiny muted">{e.note}</p>}
          </div>
        )}
      </Card>

      <Card title="Recent AI calls (AI_LOG in Exasol)">
        {log.error ? <ErrorCard error={log.error} /> : !log.data ? <RowsSkeleton rows={4} /> : log.data.calls.length === 0 ? <p className="muted small">No AI calls yet.</p> : (
          <div className="table-wrap" style={{ maxHeight: 360 }}>
            <table className="ledger">
              <thead><tr><th>When (UTC)</th><th>Feature</th><th>Model</th><th>Prompt</th><th>Input</th><th className="r">Time</th><th>Status</th></tr></thead>
              <tbody>{log.data.calls.map((c) => (
                <tr key={c.call_id}><td className="small">{dateTime(c.created)}</td><td className="small">{c.feature}</td><td className="small mono">{c.model}</td>
                  <td className="small mono">{c.prompt_version}</td><td className="small">{c.input_ref}</td><td className="r num small">{(c.ms / 1000).toFixed(1)} s</td><td className="small">{c.status}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
