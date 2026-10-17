// Types mirroring the API responses in backend/app/main.py.

export type Status = 'DETERMINED' | 'RANGE' | 'UNDETERMINABLE' | 'OUT_OF_SCOPE';
export type Classification = 'WITHIN_EVIDENCE' | 'WITHIN_RANGE' | 'EXCEEDS_EVIDENCE' | 'CANNOT_DETERMINE';
export type RequestStatus = 'COMPLETE' | 'INCOMPLETE' | 'CONFLICTING';
export type TerminalState = 'INTERNAL' | 'OUT_OF_SCOPE' | 'CASH_OUT' | 'CHARGES' | 'RETURNED_TO_VICTIM';
export type Convention = 'PR' | 'FIFO' | 'LIFO';
export type Scenario =
  | 'SIMPLE_CHAIN' | 'SPLIT_MERGE' | 'COMMINGLED' | 'INNOCENT_RECIPIENT' | 'BUSINESS_TURNOVER'
  | 'RAPID_CASHOUT' | 'CROSS_INSTITUTION' | 'REVERSAL_FAILED' | 'SHARED_ACCOUNT' | 'WORKED_EXAMPLE';

export interface Health {
  db: string;
  exasol_version: string;
  schema: string;
  latest_run_id: number | null;
  row_counts: { accounts: number; transactions: number; [k: string]: number };
}

export interface RunSummary {
  run_id: number;
  started: string;
  finished: string | null;
  duration_s: number | null;
  status: 'DONE' | 'RUNNING' | 'FAILED' | string;
}

export interface Overview {
  counts: {
    accounts: number; transactions: number; cases: number; requests: number;
    request_targets: number; restraints: number; institutions: number;
  };
  run: RunSummary | null;
  totals: {
    reported_loss: number; whole_balance_locked: number; requested_total: number;
    supported_lower: number; supported_upper: number; unsupported_locked: number;
  };
  status_breakdown: { status: Status; n: number }[];
  classification_breakdown: { classification: Classification; n: number }[];
  request_status_breakdown: { request_status: RequestStatus; n: number }[];
  scenario_breakdown: { scenario: Scenario; n: number }[];
  conservation: { checks: number; passed: number };
  layer_profile: { layer: number; n_accounts: number; avg_share_pr: number; avg_share_fifo: number }[];
}

export interface CaseListItem {
  case_id: number; case_ref: string; scenario: Scenario; reported_loss: number;
  fraud_ts: string; ref_ts: string; request_status: RequestStatus; n_accounts: number;
  max_layer: number; requested_total: number; supported_lower: number; supported_upper: number;
  worst_classification: Classification | null; n_out_of_scope: number;
}
export interface CaseList { total: number; page: number; page_size: number; items: CaseListItem[] }
export interface CaseQuery {
  search?: string; scenario?: string; classification?: string; request_status?: string;
  page?: number; page_size?: number; sort?: 'loss' | 'fraud_ts' | 'overbroad';
}

export interface CompletenessItem { code: string; label: string; kind: 'MISSING' | 'CONFLICT' | 'OK'; detail: string }

export interface TrailNode {
  account_id: string; institution: string; observable: boolean; account_type: string;
  is_victim: boolean; layer: number; balance: number;
  retained_pr: number; retained_fifo: number; retained_lifo: number;
  lower: number; upper: number; lower_ext: number; upper_ext: number;
  share_lo: number; share_hi: number; sensitivity: number;
  status: Status; status_reasons: string[];
  requested_scope: 'WHOLE_BALANCE' | 'AMOUNT' | null; requested_amount: number | null;
  classification: Classification | null; ratio_to_upper: number | null;
  in_transit: { pr: number; fifo: number; lifo: number };
  combined?: { cases: number; lower: number | null; upper: number | null } | null;
}

export interface TrailEdge {
  txn_id: string; from: string; to: string; ts: string; amount: number; channel: string;
  layer: number; carried_pr: number; carried_fifo: number; carried_lifo: number;
  terminal_state: TerminalState; flags: string[];
}

export interface ConservationRow {
  convention: Convention; loss: number; retained: number; exited: number;
  dust: number; absorbed: number; difference: number; passed: boolean;
}

export interface ReviewRow {
  account_id: string; requested_scope: string | null; requested_amount: number | null;
  lower: number; upper: number; classification: Classification | null; ratio_to_upper: number | null;
  reasons: string[];
  facts: {
    cases_through_account: number; share_moved_within_minutes: number; minutes_window: number;
    commingling: number; separable: boolean;
  };
}

export interface ForwardedRow {
  txn_id: string; destination_account: string; destination_institution: string; amount: number;
  carried_pr: number; carried_fifo: number; carried_lifo: number; ts: string; reference: string;
  checklist_missing: string[]; draft: string;
}

export interface CaseDetail {
  case: {
    case_id: number; case_ref: string; scenario: Scenario; victim_account: string;
    reported_loss: number; fraud_ts: string; ref_ts: string; ref_rule: string;
  };
  request: {
    request_id: number; received_ts: string; issuing_officer: string | null; designation: string | null;
    agency: string | null; agency_contact: string | null; case_reference: string | null;
    legal_provision: string | null; action_type: string; stated_amount: number | null;
    completeness: { status: RequestStatus; items: CompletenessItem[]; clarification_draft: string };
  } | null;
  nodes: TrailNode[];
  edges: TrailEdge[];
  review: ReviewRow[];
  dilution: { layer: number; n_accounts: number; share_pr: number; share_fifo: number; below_threshold: number }[];
  forwarded: ForwardedRow[];
  conservation: ConservationRow[];
  assumptions: string[];
}

export interface Explanation { account_id: string; text: string }

export interface PgAccount { name: string; opening: number }
export interface PgTransfer { from: string; to: string; amount: number; minute: number }
export interface PgTarget { account: string; scope: 'WHOLE_BALANCE' | 'AMOUNT'; amount?: number }
export interface PgRequest {
  officer: string; designation: string; agency: string; contact: string; reference: string;
  legal_provision: string; action_type: string; stated_amount: number | null; targets: PgTarget[];
}
export interface PgBody { accounts: PgAccount[]; transfers: PgTransfer[]; request: PgRequest }
export interface PgScenario extends PgBody { id: string; title: string; summary: string; teaches: string }
export interface PgStep {
  txn_id: string; when: string | null; kind: 'IN' | 'OUT'; amount: number; counterparty: string;
  balance_after: number; disputed_pr_after: number; disputed_fifo_after: number; text: string;
  calc: { pro_rata: string; fifo: string } | null;
}
export interface PgAccountResult {
  account_id: string; opening: number; received: boolean; balance: number | null;
  retained_pr: number; retained_fifo: number; retained_lifo: number; lower: number | null; upper: number | null;
  share_lo: number | null; share_hi: number | null; status: Status | 'NOT_REACHED'; layer: number | null;
  reasons: string[]; steps: PgStep[]; summary: string;
}
export interface PgEdge {
  txn_id: string; from: string; to: string; minute: number; time: string; amount: number; layer: number;
  carried_pr: number; carried_fifo: number; carried_lifo: number; terminal_state: TerminalState;
}
export interface PgResult {
  loss: number; ref_minute: number; ref_time: string;
  request_check: { status: RequestStatus | null; items: CompletenessItem[]; draft: string };
  accounts: PgAccountResult[]; edges: PgEdge[];
  review: { account_id: string; scope: string; requested: number | null; lower: number | null; upper: number | null;
            classification: Classification; ratio_to_upper: number | null; reasons: string[] }[];
  forwarded: string[]; conservation: ConservationRow[];
  totals: { whole_balance: number; traced_pr: number; traced_fifo: number; requested: number };
  engine: { layer_passes: number; sql_steps: { step: string; ms: number; rows: number | null }[]; load_ms: number;
            engine_ms: number; total_ms: number; schema: string; steps: BasisStep[]; rules: BasisRule[] };
}
export interface BasisStep { step: string; file: string | null; ms: number; rows: number | null; passes: number | null; pass_rows: (number | null)[] | null; purpose: string }
export interface BasisRule { rule: string; value: string; why: string }
export interface CaseBasis {
  run: { run_id: number; started: string; duration_s: number; checksum: string } | null;
  facts: { transfers: number; accounts: number; layers: number; postings: number; transactions_total: number };
  steps: BasisStep[]; rules: BasisRule[]; page_query: string;
  source_check?: { run_id: number; tables: number; rows: number; unchanged: boolean } | null;
}
export interface SqlScript { name: string; purpose: string; sql: string }
export interface Explanation2 { account_id: string; steps: PgStep[]; summary: string | null }

export type LienFlag = 'ALL' | 'OVER_HOLD' | 'CLOSED_STILL_HELD' | 'PAST_90' | 'PAST_REVIEW' | 'ESCALATE';
export interface LienItem {
  restraint_id: number; account_id: string; case_id: number; case_ref: string;
  held_amount: number; lower: number; upper: number; over_hold_ratio: number | null;
  days_held: number; days_since_update: number; closure_status: string;
  band: 'UNDER_50K' | 'OVER_50K'; days_to_90: number | null; escalation_date: string | null;
  flags: string[]; priority: number;
}
export interface LienReview {
  as_of: string; total: number;
  summary: { over_hold: number; closed_still_held: number; past_review: number; escalate: number; [k: string]: number };
  items: LienItem[];
}

export interface Oversight {
  over_hold_hist: { bucket: string; n: number }[];
  age_hist: { bucket: string; n: number }[];
  missing_fields_share: number; no_update_share: number;
  by_status: { closure_status: string; n: number; avg_over_hold: number }[];
}

export interface PolicySim {
  hold_time: string; note: string;
  policies: {
    policy: 'WHOLE_BALANCE' | 'REQUESTED' | 'LOWER' | 'UPPER' | string; label: string;
    disputed_held: number; non_disputed_locked: number; accounts_restricted: number;
    by_scenario: { scenario: string; disputed_held: number; non_disputed_locked: number }[];
  }[];
}

export interface Speed { curves: { scenario: string; points: { minutes: number; share_inside: number }[] }[] }

export interface Sensitivity {
  hist: { bucket: string; n: number }[];
  by_layer: { layer: number; avg_sensitivity: number }[];
  top: { case_id: number; account_id: string; lower_ext: number; upper_ext: number; sensitivity: number }[];
}

export interface Run {
  run_id: number; started: string; finished: string | null; status: 'DONE' | 'RUNNING' | 'FAILED' | string;
  snapshot_id: string | null; software_version: string | null; checksum: string | null;
  duration_s: number | null; config: Record<string, unknown> | null;
}
export interface Fingerprint { table: string; rows_before: number | null; rows_after: number | null; fingerprint_before: string | null; fingerprint_after: string | null; unchanged: boolean }
export interface RunDetail extends Run {
  steps: { step: string; ms: number; rows: number | null }[];
  fingerprints?: Fingerprint[]; source_unchanged?: boolean | null;
  history_rows?: { sizing: number; review: number; cases: number; trail: number } | null;
  compared_with?: { run_id: number; same_snapshot: boolean; identical_results: boolean };
}
export interface ProtectionCheck { action: string; statement: string; expected: string; result: string; ok: boolean; exasol_says: string }
export interface Protection { ready: boolean; note?: string; engine_user?: string; all_ok?: boolean; checks?: ProtectionCheck[];
  schemas?: { schema: string; holds: string; engine: string }[] }
export interface RunCompare { a: number; b: number; rows_a: number; rows_b: number; changed: number; reclassified: number; identical: boolean }
export interface LiveAnalysis { analysis_id: number; created: string; case_title: string; engine_ms: number;
  summary: { loss?: number; totals?: { requested: number; traced_pr: number; traced_fifo: number }; request_status?: string; conservation_ok?: boolean;
    review?: { account_id: string; requested: number | null; upper: number | null; classification: string }[] } }

export interface Evaluation {
  generated_at: string; note: string;
  request_defects: { defect: string; planted: number; detected: number; false_pos: number; precision: number; recall: number }[];
  path: { scenario: string; precision: number; recall: number; tp: number; fp: number; fn: number }[];
  amount: { convention: string; mae: number; max_abs_err: number; within_1_rupee: number; within_1_paisa?: number; range_coverage: number }[];
  conservation: { checks: number; passed: number };
  abstention: { planted: number; correctly_undeterminable: number; determinable: number; wrongly_undeterminable: number };
  overbroad: { planted: number; flagged: number; recall: number };
}

export interface Benchmark {
  hardware: unknown;
  results: { engine: string; tier: string; workload: string; rows: number; median_s: number; min_s: number; max_s: number; runs: number }[];
  full_run?: { run_id: number; transactions: number; duration_s: number; core_s: number } | null;
}

// ---------------------------------------------------------------- AI at the edges
export interface AiStatus {
  llm: { enabled: boolean; provider: string; model: string; reason: string | null; temperature: number; seed: number };
  mcp: { running: boolean; package: string; user: string; tools: number; error: string | null };
  reader_ready: boolean;
  counts: { letters: number; extractions: number; confirmations: number; ai_calls: number; questions: number } | null;
}
export interface ExtractCheck { check: string; ok: boolean; detail: string }
export interface ExtractItem { value: unknown; raw_value: string; span: string; start: number; end: number; checks: ExtractCheck[]; verified: boolean; records_ok: boolean }
export type ExtractStatus = 'VERIFIED' | 'UNVERIFIED' | 'CONFLICT' | 'NOT_STATED' | 'PARTLY';
export interface ExtractField { field: string; label: string; status: ExtractStatus; value: unknown; items: ExtractItem[]; reasons: string[] }
export interface Extraction { extraction_id: number; model: string; prompt_version: string; ms: number; fields: ExtractField[]; text: string }
export interface SampleLetter { id: string; title: string; style: string; text: string }
export interface AskResult {
  question: string; mode: 'TEMPLATE' | 'SQL' | 'REFUSED'; template_id?: string | null; params?: Record<string, unknown>;
  sql: string | null; columns: string[]; rows: unknown[][]; row_count: number; answer: string; ai_wording?: string;
  fidelity: { ok: boolean; unsupported: string[] }; via?: string; model?: string; ms?: number;
}
export interface RewordResult { template: string; reworded: string; text: string; used: 'AI' | 'TEMPLATE'; model: string; prompt_version: string;
  check: { ok: boolean; problems: string[]; facts_checked: number } }
export interface AiLogRow { call_id: number; feature: string; model: string; prompt_version: string; input_ref: string; ms: number; status: string; created: string; output_preview: string }

export interface HoldItem { account_id: string; requested: number | null; balance: number | null; lower: number | null; upper: number | null; status: string | null }
export interface HoldPlanRow extends HoldItem { proposed: number | null; released?: number; note: string }
export interface HoldDraftResult { basis: string; plan: HoldPlanRow[]; text: string; totals: { requested: number; proposed: number; released: number; not_sized: number } }

export interface RetraceResult { case_id: number; ms: number; layers: number; ledger_transactions: number; steps: BasisStep[]; identical: boolean; schema: string;
  accounts: { account_id: string; layer: number; retained_pr: number | null; retained_fifo: number | null; lower: number | null; upper: number | null; status: string; matches_stored: boolean }[] }

export interface ExasolAtWork {
  version: string;
  db_size: { raw_gib: string; mem_gib: string; ram_gib: string; storage_gib: string; objects: number } | null;
  source_tables: { name: string; row_count: number; raw: number; mem: number }[];
  work_tables: { name: string; row_count: number; raw: number; mem: number }[];
  indexes: { total: number; by_schema: Record<string, number>; created_by_tracehold: number; largest: { sch: string; tbl: string; kind: string; mem: number; remarks: string }[] };
  last_run: { run_id: number; statements: number; seconds: number; rows: number; temp_peak_mib: number;
    by_command: { command: string; n: number; seconds: number | null; row_count: number | null }[] } | null;
}
