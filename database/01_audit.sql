-- History and audit trail. {A} = audit schema (TRACEHOLD_AUDIT for the full dataset).
-- The analysis user may only INSERT here (and update a run's status): Exasol
-- refuses any DELETE, TRUNCATE or DROP from it, so the history cannot be lost.

CREATE SCHEMA IF NOT EXISTS {A};

-- ---------------------------------------------------------------- runs
CREATE TABLE IF NOT EXISTS {A}.RUNS (
    run_id           DECIMAL(9,0),
    started          TIMESTAMP,
    finished         TIMESTAMP,
    run_status       VARCHAR(10),
    snapshot_id      VARCHAR(80),
    software_version VARCHAR(20),
    config_json      VARCHAR(4000),
    checksum         VARCHAR(80),
    duration_s       DOUBLE,
    error_text       VARCHAR(2000)
);

CREATE TABLE IF NOT EXISTS {A}.RUN_STEPS (
    run_id           DECIMAL(9,0),
    step_no          DECIMAL(5,0),
    step_name        VARCHAR(100),
    ms               DOUBLE,
    row_count        DECIMAL(18,0)
);

-- Proof that a run did not change the source data: row count and a fingerprint
-- (sum of per-row MD5 hashes) of every source table, before and after the run.
CREATE TABLE IF NOT EXISTS {A}.SOURCE_FINGERPRINTS (
    run_id           DECIMAL(9,0),
    phase            VARCHAR(6),       -- BEFORE / AFTER
    table_name       VARCHAR(40),
    row_count        DECIMAL(18,0),
    fingerprint      DECIMAL(36,0),
    taken            TIMESTAMP
);

-- ---------------------------------------------------------------- results history
-- A copy of the key results of every run, so any earlier figure can be shown again.
CREATE TABLE IF NOT EXISTS {A}.SIZING_HISTORY (
    run_id DECIMAL(9,0), case_id DECIMAL(9,0), account_id VARCHAR(20), layer DECIMAL(4,0), balance_ref DOUBLE,
    retained_pr DOUBLE, retained_fifo DOUBLE, retained_lifo DOUBLE, lower_amt DOUBLE, upper_amt DOUBLE,
    share_lo DOUBLE, share_hi DOUBLE, status VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS {A}.REVIEW_HISTORY (
    run_id DECIMAL(9,0), request_id DECIMAL(9,0), case_id DECIMAL(9,0), account_id VARCHAR(20),
    requested_scope VARCHAR(20), requested_amount DOUBLE, lower_amt DOUBLE, upper_amt DOUBLE,
    classification VARCHAR(20), ratio_to_upper DOUBLE
);

CREATE TABLE IF NOT EXISTS {A}.CASE_SUMMARY_HISTORY (
    run_id DECIMAL(9,0), case_id DECIMAL(9,0), request_status VARCHAR(20), requested_total DOUBLE,
    supported_lower DOUBLE, supported_upper DOUBLE, whole_balance DOUBLE, excess DOUBLE, conservation_ok BOOLEAN
);

CREATE TABLE IF NOT EXISTS {A}.TRAIL_HISTORY (
    run_id DECIMAL(9,0), case_id DECIMAL(9,0), txn_id VARCHAR(24), from_acct VARCHAR(20), to_acct VARCHAR(20),
    layer DECIMAL(4,0), carried_pr DOUBLE, carried_fifo DOUBLE, carried_lifo DOUBLE, terminal_state VARCHAR(20)
);

-- Every live analysis: what was entered and what came out.
CREATE TABLE IF NOT EXISTS {A}.LIVE_ANALYSES (
    analysis_id   DECIMAL(18,0),
    created       TIMESTAMP,
    case_title    VARCHAR(200) UTF8,
    input_json    VARCHAR(200000) UTF8,
    summary_json  VARCHAR(20000) UTF8,
    engine_ms     DECIMAL(12,1)
);
