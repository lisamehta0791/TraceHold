// Tiny typed API client for the TraceHold FastAPI backend (relative /api URLs).
import type {
  Benchmark, CaseDetail, CaseList, CaseQuery, Evaluation, Explanation, Health, LienFlag, LienReview,
  Overview, Oversight, PolicySim, Run, RunDetail, PgBody, PgResult, PgScenario, Explanation2, Sensitivity, Speed, CaseBasis, SqlScript,
  AiStatus, Extraction, SampleLetter, AskResult, RewordResult, AiLogRow, Protection, RunCompare, LiveAnalysis, HoldDraftResult, RetraceResult, ExasolAtWork,
} from './types';

export * from './types';


export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function qs(params: Record<string, unknown>): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
    });
  } catch {
    throw new ApiError('Could not reach the TraceHold service. Is the backend running on port 8000?', 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body);
    } catch { /* ignore */ }
    throw new ApiError(`${res.status} ${detail}`, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: (): Promise<Health> => http('/health'),
  overview: (): Promise<Overview> => http('/overview'),
  cases: (q: CaseQuery = {}): Promise<CaseList> => http(`/cases${qs({ ...q })}`),
  caseDetail: (id: number | string): Promise<CaseDetail> =>
    http(`/cases/${encodeURIComponent(String(id))}`),
  packet: (id: number | string): Promise<unknown> =>
    http(`/cases/${encodeURIComponent(String(id))}/packet`),
  packetHtmlUrl: (id: number | string) => `/api/cases/${encodeURIComponent(String(id))}/packet.html`,
  explanation: (id: number | string, account: string): Promise<Explanation> =>
    http(`/cases/${encodeURIComponent(String(id))}/explanation/${encodeURIComponent(account)}`),
  scenarios: (): Promise<{ scenarios: PgScenario[] }> => http('/playground/scenarios'),
  runPlayground: (body: PgBody): Promise<PgResult> =>
    http('/playground/run', { method: 'POST', body: JSON.stringify(body) }),
  caseExplain: (id: number | string, account: string): Promise<Explanation2> =>
    http(`/cases/${encodeURIComponent(String(id))}/explain/${encodeURIComponent(account)}`),
  lienReview: (q: { flag?: LienFlag; page?: number; page_size?: number } = {}): Promise<LienReview> =>
    http(`/lien-review${qs(q)}`),
  oversight: (): Promise<Oversight> => http('/oversight'),
  policySim: (): Promise<PolicySim> => http('/policy-sim'),
  speed: (): Promise<Speed> => http('/speed'),
  sensitivity: (): Promise<Sensitivity> => http('/sensitivity'),
  runs: (): Promise<{ runs: Run[] }> => http('/runs'),
  startRun: (mode: 'python' | 'lua' = 'python'): Promise<{ run_id: number }> => http('/runs', { method: 'POST', body: JSON.stringify({ mode }) }),
  run: (id: number): Promise<RunDetail> => http(`/runs/${id}`),
  caseBasis: (id: number | string): Promise<CaseBasis> => http(`/cases/${encodeURIComponent(String(id))}/basis`),
  sqlScript: (name: string, where: 'cases' | 'playground' = 'cases'): Promise<SqlScript> =>
    http(`/basis/sql/${encodeURIComponent(name)}${qs({ where })}`),
  caseHoldDraft: (id: number, basis: string, overrides: Record<string, number>): Promise<HoldDraftResult> =>
    http(`/cases/${id}/hold-draft`, { method: 'POST', body: JSON.stringify({ basis, overrides }) }),
  holdDraft: (body: Record<string, unknown>): Promise<HoldDraftResult> => http('/hold-draft', { method: 'POST', body: JSON.stringify(body) }),
  retrace: (id: number): Promise<RetraceResult> => http(`/cases/${id}/retrace`, { method: 'POST' }),
  exasol: (): Promise<ExasolAtWork> => http('/exasol'),
  protection: (): Promise<Protection> => http('/protection'),
  compareRuns: (a: number, b: number): Promise<RunCompare> => http(`/history/compare${qs({ a, b })}`),
  liveAnalyses: (limit = 20): Promise<{ analyses: LiveAnalysis[] }> => http(`/live-analyses${qs({ limit })}`),
  aiStatus: (): Promise<AiStatus> => http('/ai/status'),
  sampleLetters: (scenario: string): Promise<{ letters: SampleLetter[] }> => http(`/ai/letters${qs({ scenario })}`),
  caseLetter: (id: number | string): Promise<{ letter: { doc_id: number; request_id: number; split: string; body: string } | null }> =>
    http(`/cases/${encodeURIComponent(String(id))}/letter`),
  extract: (text: string, context?: Record<string, unknown>, doc_id?: number): Promise<Extraction> =>
    http('/ai/extract', { method: 'POST', body: JSON.stringify({ text, context, doc_id }) }),
  confirmExtraction: (id: number, fields: Record<string, unknown>, confirmed_by: string): Promise<{ confirmed: number; corrected: number }> =>
    http(`/ai/extract/${id}/confirm`, { method: 'POST', body: JSON.stringify({ fields, confirmed_by }) }),
  askTemplates: (): Promise<{ templates: { id: string; question: string }[]; views: { name: string; about: string }[] }> => http('/ai/ask/templates'),
  ask: (question: string): Promise<AskResult> => http('/ai/ask', { method: 'POST', body: JSON.stringify({ question }) }),
  reword: (id: number | string, account: string): Promise<RewordResult> =>
    http(`/cases/${encodeURIComponent(String(id))}/explanation/${encodeURIComponent(account)}/reword`, { method: 'POST' }),
  aiLog: (limit = 30): Promise<{ calls: AiLogRow[] }> => http(`/ai/log${qs({ limit })}`),
  aiEvaluation: (): Promise<Record<string, unknown> & { available: boolean }> => http('/ai/evaluation'),
  evaluation: (): Promise<Evaluation> => http('/evaluation'),
  benchmark: (): Promise<Benchmark> => http('/benchmark'),
};
