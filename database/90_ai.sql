-- ============================================================================
-- AI at the edges (CF9, AF7, AF8): storage for synthetic letters, extraction
-- results with source spans, person confirmations, the AI call log and the
-- question log; plus a results-only view schema for governed questions.
-- No model ever writes to a table that holds a figure.
-- Parameters: {S}, {GT}, {R} (results view schema)
-- ============================================================================

CREATE TABLE IF NOT EXISTS {S}.REQUEST_DOCUMENTS (
    doc_id      DECIMAL(9,0) PRIMARY KEY,
    request_id  DECIMAL(9,0),
    case_id     DECIMAL(9,0),
    split       VARCHAR(10),          -- DEV (prompt tuning) or HELDOUT (reported results)
    body        VARCHAR(20000) UTF8
);

CREATE TABLE IF NOT EXISTS {S}.EXTRACTION_RESULTS (
    extraction_id  DECIMAL(18,0),
    doc_id         DECIMAL(9,0),      -- NULL for a pasted letter
    field_name     VARCHAR(40),
    value_text     VARCHAR(2000) UTF8,
    span_text      VARCHAR(2000) UTF8,
    span_start     DECIMAL(9,0),
    span_end       DECIMAL(9,0),
    status         VARCHAR(12),       -- VERIFIED, UNVERIFIED, CONFLICT, NOT_STATED
    reasons        VARCHAR(2000) UTF8,
    model          VARCHAR(80),
    prompt_version VARCHAR(20),
    created        TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {S}.EXTRACTION_CONFIRMATIONS (
    extraction_id   DECIMAL(18,0),
    field_name      VARCHAR(40),
    confirmed_value VARCHAR(2000) UTF8,
    corrected       BOOLEAN,
    confirmed_by    VARCHAR(100) UTF8,
    confirmed_at    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {S}.AI_LOG (
    call_id        DECIMAL(18,0),
    feature        VARCHAR(10),       -- CF9, AF7, AF8
    model          VARCHAR(80),
    prompt_version VARCHAR(20),
    input_ref      VARCHAR(200) UTF8,
    input_text     VARCHAR(200000) UTF8,
    output_text    VARCHAR(200000) UTF8,
    temperature    DECIMAL(3,2),
    ms             DECIMAL(12,1),
    status         VARCHAR(20),       -- OK, ERROR, RATE_LIMITED
    created        TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {S}.ASK_LOG (
    ask_id       DECIMAL(18,0),
    question     VARCHAR(2000) UTF8,
    mode         VARCHAR(12),         -- TEMPLATE, SQL, REJECTED
    template_id  VARCHAR(40),
    sql_text     VARCHAR(20000) UTF8,
    row_count    DECIMAL(9,0),
    answer_text  VARCHAR(20000) UTF8,
    fidelity_ok  BOOLEAN,
    model        VARCHAR(80),
    ms           DECIMAL(12,1),
    created      TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {GT}.LETTER_TRUTH (
    doc_id      DECIMAL(9,0),
    field_name  VARCHAR(40),
    true_value  VARCHAR(2000) UTF8
);

-- ---------------------------------------------------------------- results-only views (AF7)
-- The question-answering user can read these views and nothing else: no raw
-- transactions, no requests, and never the ground-truth schema.
CREATE SCHEMA IF NOT EXISTS {R};

CREATE OR REPLACE VIEW {R}.CASES AS
SELECT case_id, case_ref, loss AS reported_loss, request_status, n_accounts, max_layer, n_undeterminable,
       requested_total, supported_lower, supported_upper, whole_balance, excess AS unsupported_amount,
       n_targets, n_exceeds, worst_classification, n_out_of_scope, conservation_ok
FROM {S}.CASE_SUMMARY;

CREATE OR REPLACE VIEW {R}.ACCOUNT_SIZING AS
SELECT z.case_id, r.case_ref, z.account_id, z.layer, z.balance_ref AS balance, z.retained_pr, z.retained_fifo,
       z.retained_lifo, z.lower_amt AS supported_lower, z.upper_amt AS supported_upper,
       z.share_lo, z.share_hi, z.status
FROM {S}.SIZING z JOIN {S}.CASE_REF r ON r.case_id = z.case_id;

CREATE OR REPLACE VIEW {R}.REVIEW_FLAGS AS
SELECT v.request_id, v.case_id, r.case_ref, v.account_id, v.layer, v.requested_scope, v.requested_amount,
       v.lower_amt AS supported_lower, v.upper_amt AS supported_upper, v.classification, v.ratio_to_upper,
       v.excess_over_upper, v.cases_through_account
FROM {S}.REVIEW v JOIN {S}.CASE_REF r ON r.case_id = v.case_id;

CREATE OR REPLACE VIEW {R}.RESTRAINTS AS
SELECT restraint_id, account_id, case_id, restraint_type, held_amount, start_date, last_update_date,
       closure_status, active, band, days_held, days_since_update, lower_amt AS supported_lower,
       upper_amt AS supported_upper, over_hold_ratio, days_to_90, escalation_date,
       f_over_hold AS over_hold, f_closed_still_held AS closed_still_held, f_past_90 AS past_90_days,
       f_past_review AS past_review_date, f_escalate AS escalate, priority
FROM {S}.LIEN_REVIEW;

CREATE OR REPLACE VIEW {R}.REQUESTS AS
SELECT request_id, case_id, status AS request_status, n_missing, n_conflict FROM {S}.REQ_STATUS;
