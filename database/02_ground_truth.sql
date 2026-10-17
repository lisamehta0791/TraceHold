-- The generator's answer key. {GT} = ground-truth schema.
-- Written by the loader, read only by the evaluation harness. The analysis user
-- has no privilege on it (except the scenario labels shown in the case list).
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

