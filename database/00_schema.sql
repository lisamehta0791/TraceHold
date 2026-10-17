-- TraceHold base schema. {S} = analysis schema, {GT} = ground-truth schema.
-- The analysis SQL only ever reads {S}; {GT} is written by the generator and
-- read only by the evaluation harness.

CREATE SCHEMA IF NOT EXISTS {S};

CREATE OR REPLACE TABLE {S}.INSTITUTIONS (
    institution_id   VARCHAR(10) NOT NULL,
    inst_name        VARCHAR(80),
    inst_kind        VARCHAR(12),          -- BANK | WALLET
    observable       BOOLEAN,              -- records available to the reviewer
    CONSTRAINT pk_inst PRIMARY KEY (institution_id) DISABLE
);

CREATE OR REPLACE TABLE {S}.ACCOUNTS (
    account_id       VARCHAR(20) NOT NULL,
    institution_id   VARCHAR(10),
    holder_label     VARCHAR(80),          -- synthetic label, never a real person
    acct_type        VARCHAR(12),          -- INDIVIDUAL | BUSINESS
    opened_date      DATE,
    opening_balance  DECIMAL(18,2),        -- NULL = balance snapshot missing
    opening_ts       TIMESTAMP,
    opening_epoch    DECIMAL(12,0),
    closing_balance  DECIMAL(18,2),        -- statement balance at closing_ts
    closing_ts       TIMESTAMP,
    CONSTRAINT pk_acc PRIMARY KEY (account_id) DISABLE
);

CREATE OR REPLACE TABLE {S}.TRANSACTIONS (
    txn_id           VARCHAR(24) NOT NULL,
    seq_id           DECIMAL(18,0),        -- posting sequence, deterministic tie-break
    ts               TIMESTAMP,
    ts_epoch         DECIMAL(12,0),        -- seconds since 2026-01-01, for portable arithmetic
    from_acct        VARCHAR(20),          -- NULL for interest / external credits
    to_acct          VARCHAR(20),          -- NULL for cash withdrawal and charges
    amount           DECIMAL(18,2),
    channel          VARCHAR(12),          -- UPI IMPS NEFT RTGS CARD CASH_WD WALLET CHARGE INTEREST
    txn_ref          VARCHAR(40),
    txn_status       VARCHAR(10),          -- COMPLETED FAILED PENDING
    reversal_of      VARCHAR(24),          -- set on a reversal posting
    CONSTRAINT pk_txn PRIMARY KEY (txn_id) DISABLE
);

CREATE OR REPLACE TABLE {S}.CASES (
    case_id          DECIMAL(9,0) NOT NULL,
    case_ref         VARCHAR(40),
    victim_account   VARCHAR(20),
    reported_loss    DECIMAL(18,2),
    fraud_ts         TIMESTAMP,
    fraud_epoch      DECIMAL(12,0),
    CONSTRAINT pk_case PRIMARY KEY (case_id) DISABLE
);

-- The transactions the victim reported as fraudulent (layer 0 -> layer 1).
CREATE OR REPLACE TABLE {S}.CASE_DISPUTED_TXNS (
    case_id          DECIMAL(9,0),
    txn_id           VARCHAR(24)
);

CREATE OR REPLACE TABLE {S}.REQUESTS (
    request_id       DECIMAL(9,0) NOT NULL,
    case_id          DECIMAL(9,0),
    received_ts      TIMESTAMP,
    received_epoch   DECIMAL(12,0),
    issuing_officer  VARCHAR(80),
    designation      VARCHAR(60),
    agency           VARCHAR(100),
    agency_contact   VARCHAR(100),
    case_reference   VARCHAR(40),          -- FIR / NCRP / CFCFRMS reference as quoted
    legal_provision  VARCHAR(100),
    action_type      VARCHAR(20),          -- LIEN_AMOUNT | DEBIT_FREEZE | TOTAL_FREEZE
    stated_amount    DECIMAL(18,2),        -- disputed amount as stated in the request
    quoted_txn_id    VARCHAR(24),          -- disputed transaction as quoted
    CONSTRAINT pk_req PRIMARY KEY (request_id) DISABLE
);

CREATE OR REPLACE TABLE {S}.REQUEST_TARGETS (
    request_id       DECIMAL(9,0),
    account_id       VARCHAR(20),
    requested_scope  VARCHAR(16),          -- AMOUNT | WHOLE_BALANCE
    requested_amount DECIMAL(18,2),        -- NULL when WHOLE_BALANCE
    quoted_txn_id    VARCHAR(24)           -- transfer by which the account received funds
);

CREATE OR REPLACE TABLE {S}.RESTRAINTS (
    restraint_id     DECIMAL(9,0) NOT NULL,
    account_id       VARCHAR(20),
    case_id          DECIMAL(9,0),
    request_id       DECIMAL(9,0),
    restraint_type   VARCHAR(20),          -- LIEN_AMOUNT | DEBIT_FREEZE | TOTAL_FREEZE
    held_amount      DECIMAL(18,2),
    start_date       DATE,
    last_update_date DATE,
    issuing_authority VARCHAR(100),
    closure_status   VARCHAR(16),          -- OPEN | CLOSURE_REPORT | CLEAN_CHIT | CLOSED
    released_date    DATE,
    CONSTRAINT pk_rst PRIMARY KEY (restraint_id) DISABLE
);

-- Configurable completeness checklist (CF1). Default mirrors the items the
-- Rajasthan High Court lists for a police communication to a bank.
CREATE OR REPLACE TABLE {S}.CHECKLIST_ITEMS (
    item_code        VARCHAR(30),
    field_name       VARCHAR(30),
    label            VARCHAR(80),
    required         BOOLEAN,
    sort_order       DECIMAL(3,0)
);

CREATE OR REPLACE TABLE {S}.DATASET_INFO (
    info_key         VARCHAR(40),
    info_value       VARCHAR(2000)
);

-- ---------------------------------------------------------------- run log
CREATE TABLE IF NOT EXISTS {S}.RUNS (
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

CREATE TABLE IF NOT EXISTS {S}.RUN_STEPS (
    run_id           DECIMAL(9,0),
    step_no          DECIMAL(5,0),
    step_name        VARCHAR(100),
    ms               DOUBLE,
    row_count        DECIMAL(18,0)
);

-- ---------------------------------------------------------------- ground truth
CREATE SCHEMA IF NOT EXISTS {GT};

CREATE OR REPLACE TABLE {GT}.CASE_SCENARIO (
    case_id          DECIMAL(9,0),
    scenario         VARCHAR(30)
);

-- Transfers the generator designated as part of the fraud chain.
CREATE OR REPLACE TABLE {GT}.CHAIN_TXNS (
    case_id          DECIMAL(9,0),
    txn_id           VARCHAR(24),
    layer            DECIMAL(4,0)
);

-- Provenance ledger: disputed funds per case/account at the case reference time,
-- computed by the generator's own (independent, row-by-row) implementation.
CREATE OR REPLACE TABLE {GT}.LEDGER (
    case_id          DECIMAL(9,0),
    account_id       VARCHAR(20),
    convention       VARCHAR(4),
    retained         DOUBLE
);

CREATE OR REPLACE TABLE {GT}.PLANTED_DEFECTS (
    defect_type      VARCHAR(40),
    case_id          DECIMAL(9,0),
    request_id       DECIMAL(9,0),
    account_id       VARCHAR(20),
    txn_id           VARCHAR(24),
    detail           VARCHAR(200)
);

