-- ============================================================================
-- Stage 1: clean transactions, per-account event ledger, running balances.
-- Parameters: {S} schema, {DUP_WINDOW} seconds, {SKEW_TOL} seconds,
--             {REF_EXPR} SQL expression for a case's reference epoch.
-- Portable SQL: runs on Exasol (primary) and PostgreSQL (benchmark baseline).
-- ============================================================================

-- Observable accounts: records held by the reviewer.
DROP TABLE IF EXISTS {S}.OBS_ACC;
CREATE TABLE {S}.OBS_ACC AS
SELECT a.account_id,
       CAST(COALESCE(a.opening_balance, 0) AS DOUBLE PRECISION) AS opening,
       CASE WHEN a.opening_balance IS NULL THEN 1 ELSE 0 END    AS missing_opening,
       CAST(a.closing_balance AS DOUBLE PRECISION)              AS closing
FROM {S}.ACCOUNTS a
JOIN {S}.INSTITUTIONS i ON i.institution_id = a.institution_id
WHERE i.observable = TRUE;

-- Duplicate postings: same parties, amount and reference within the window.
DROP TABLE IF EXISTS {S}.TXN_DUP;
CREATE TABLE {S}.TXN_DUP AS
WITH cand AS (
    SELECT COALESCE(from_acct, '-') AS f, COALESCE(to_acct, '-') AS t, amount, txn_ref
    FROM {S}.TRANSACTIONS
    WHERE txn_status = 'COMPLETED' AND reversal_of IS NULL
    GROUP BY COALESCE(from_acct, '-'), COALESCE(to_acct, '-'), amount, txn_ref
    HAVING COUNT(*) > 1
)
SELECT txn_id, first_txn
FROM (
    SELECT t.txn_id, t.ts_epoch,
           ROW_NUMBER()  OVER (PARTITION BY c.f, c.t, c.amount, c.txn_ref ORDER BY t.ts_epoch, t.seq_id) AS rn,
           FIRST_VALUE(t.txn_id)   OVER (PARTITION BY c.f, c.t, c.amount, c.txn_ref ORDER BY t.ts_epoch, t.seq_id) AS first_txn,
           FIRST_VALUE(t.ts_epoch) OVER (PARTITION BY c.f, c.t, c.amount, c.txn_ref ORDER BY t.ts_epoch, t.seq_id) AS first_epoch
    FROM {S}.TRANSACTIONS t
    JOIN cand c ON c.f = COALESCE(t.from_acct, '-') AND c.t = COALESCE(t.to_acct, '-')
               AND c.amount = t.amount AND c.txn_ref = t.txn_ref
    WHERE t.txn_status = 'COMPLETED' AND t.reversal_of IS NULL
) d
WHERE rn > 1 AND ts_epoch - first_epoch <= {DUP_WINDOW};

-- Completed reversals reduce the original transfer.
DROP TABLE IF EXISTS {S}.TXN_REV;
CREATE TABLE {S}.TXN_REV AS
SELECT reversal_of AS txn_id, SUM(CAST(amount AS DOUBLE PRECISION)) AS reversed
FROM {S}.TRANSACTIONS
WHERE txn_status = 'COMPLETED' AND reversal_of IS NOT NULL
GROUP BY reversal_of;

DROP TABLE IF EXISTS {S}.TXN_CLEAN;
CREATE TABLE {S}.TXN_CLEAN AS
SELECT t.txn_id, t.seq_id, t.ts_epoch, t.from_acct, t.to_acct, t.channel, t.txn_ref,
       CAST(t.amount AS DOUBLE PRECISION) - COALESCE(r.reversed, 0) AS amount,
       COALESCE(r.reversed, 0) AS reversed
FROM {S}.TRANSACTIONS t
LEFT JOIN {S}.TXN_REV r ON r.txn_id = t.txn_id
WHERE t.txn_status = 'COMPLETED'
  AND t.reversal_of IS NULL
  AND NOT EXISTS (SELECT 1 FROM {S}.TXN_DUP d WHERE d.txn_id = t.txn_id)
  AND CAST(t.amount AS DOUBLE PRECISION) - COALESCE(r.reversed, 0) > 0.004;

-- One row per (account, posting), debit or credit, observable accounts only.
DROP TABLE IF EXISTS {S}.EV0;
CREATE TABLE {S}.EV0 AS
SELECT t.from_acct AS account_id, t.txn_id, t.seq_id, t.ts_epoch, 'D' AS kind,
       t.amount, -t.amount AS delta, t.to_acct AS counterparty, t.channel
FROM {S}.TXN_CLEAN t JOIN {S}.OBS_ACC a ON a.account_id = t.from_acct
UNION ALL
SELECT t.to_acct, t.txn_id, t.seq_id, t.ts_epoch, 'C',
       t.amount, t.amount, t.from_acct, t.channel
FROM {S}.TXN_CLEAN t JOIN {S}.OBS_ACC a ON a.account_id = t.to_acct;

-- Naive order (timestamp, sequence) to find debits that would overdraw.
DROP TABLE IF EXISTS {S}.EV1;
CREATE TABLE {S}.EV1 AS
SELECT e.*,
       a.opening + SUM(e.delta) OVER (PARTITION BY e.account_id ORDER BY e.ts_epoch, e.seq_id, e.kind
                                      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS naive_bal
FROM {S}.EV0 e JOIN {S}.OBS_ACC a ON a.account_id = e.account_id;

-- Clock-skew correction: a debit that overdraws, and whose overdraft is cured
-- by a credit within the tolerance, is re-ordered to just after that credit.
DROP TABLE IF EXISTS {S}.SKEW_FIX;
CREATE TABLE {S}.SKEW_FIX AS
SELECT d.account_id, d.txn_id, MIN(c.ts_epoch) AS new_epoch
FROM {S}.EV1 d
JOIN {S}.EV1 c
  ON c.account_id = d.account_id AND c.kind = 'C'
 AND c.ts_epoch > d.ts_epoch AND c.ts_epoch <= d.ts_epoch + {SKEW_TOL}
WHERE d.kind = 'D' AND d.naive_bal < -0.005 AND c.naive_bal >= -0.005
GROUP BY d.account_id, d.txn_id;

-- Final ordered ledger with running balance, FIFO axes and pro-rata log factors.
-- Every window shares one specification (same partition, order and frame), so
-- the engine sorts each account's postings once.
DROP TABLE IF EXISTS {S}.EV;
CREATE TABLE {S}.EV AS
WITH r AS (
    SELECT e.account_id, e.txn_id, e.seq_id, e.ts_epoch, e.kind, e.amount, e.delta, e.counterparty, e.channel,
           COALESCE(f.new_epoch, e.ts_epoch) AS ord_epoch,
           CASE WHEN f.txn_id IS NULL THEN 0 ELSE 1 END AS skew_adjusted,
           ROW_NUMBER() OVER (PARTITION BY e.account_id
                              ORDER BY COALESCE(f.new_epoch, e.ts_epoch),
                                       CASE WHEN f.txn_id IS NULL THEN 0 ELSE 1 END, e.seq_id, e.kind) AS ev_rank,
           a.opening
    FROM {S}.EV0 e
    JOIN {S}.OBS_ACC a ON a.account_id = e.account_id
    LEFT JOIN {S}.SKEW_FIX f ON f.account_id = e.account_id AND f.txn_id = e.txn_id
), b AS (
    SELECT r.*,
           SUM(r.delta) OVER w AS cum_delta,
           SUM(CASE WHEN r.kind = 'C' THEN r.amount ELSE 0 END) OVER w AS cum_in,
           SUM(CASE WHEN r.kind = 'D' THEN r.amount ELSE 0 END) OVER w AS cum_out
    FROM r
    WINDOW w AS (PARTITION BY r.account_id ORDER BY r.ev_rank ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
), c AS (
    SELECT b.*,
           b.opening + b.cum_delta AS bal_after,
           b.opening + b.cum_delta - b.delta AS bal_before,
           GREATEST(b.opening, 0) + b.cum_in - CASE WHEN b.kind = 'C' THEN b.amount ELSE 0 END AS cin_before,
           GREATEST(-b.opening, 0) + b.cum_out - CASE WHEN b.kind = 'D' THEN b.amount ELSE 0 END AS cout_before
    FROM b
), d AS (
    SELECT c.*,
           CASE WHEN c.kind = 'D' THEN
                CASE WHEN c.bal_before <= 0.000001 THEN 1.0 ELSE LEAST(1.0, c.amount / c.bal_before) END
                ELSE 0.0 END AS share,
           CASE WHEN c.kind = 'C' AND c.bal_before < 0
                THEN LEAST(c.amount, -c.bal_before) / c.amount ELSE 0.0 END AS absorbed_frac
    FROM c
), l AS (
    SELECT d.*,
           CASE WHEN d.kind <> 'D' THEN 0.0
                WHEN 1.0 - d.share <= 0.000000000001 THEN -1000.0
                ELSE LN(1.0 - d.share) END AS lnf
    FROM d
)
SELECT l.account_id, l.txn_id, l.seq_id, l.ts_epoch, l.ord_epoch, l.ev_rank, l.kind, l.amount,
       l.counterparty, l.channel, l.skew_adjusted, l.bal_before, l.bal_after,
       l.cin_before, l.cout_before, l.share, l.absorbed_frac, l.lnf,
       SUM(l.lnf) OVER (PARTITION BY l.account_id ORDER BY l.ev_rank
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS lcum
FROM l;

-- Intermediate ledgers are no longer needed; free their memory.
DROP TABLE IF EXISTS {S}.EV1;
DROP TABLE IF EXISTS {S}.EV0;

-- Account-level data-quality flags: missing opening balance, or reconstructed
-- closing balance that does not match the statement (a gap in the records).
DROP TABLE IF EXISTS {S}.ACC_FLAGS;
CREATE TABLE {S}.ACC_FLAGS AS
SELECT a.account_id, a.missing_opening,
       a.opening + COALESCE(s.net, 0) AS recon_closing, a.closing,
       CASE WHEN a.missing_opening = 0 AND ABS(a.opening + COALESCE(s.net, 0) - COALESCE(a.closing, 0)) > 0.01
            THEN 1 ELSE 0 END AS gap,
       COALESCE(s.skew_fixes, 0) AS skew_fixes,
       COALESCE(s.overdrawn, 0) AS overdrawn
FROM {S}.OBS_ACC a
LEFT JOIN (
    SELECT account_id, SUM(CASE WHEN kind = 'D' THEN -amount ELSE amount END) AS net,
           SUM(skew_adjusted) AS skew_fixes,
           SUM(CASE WHEN bal_after < -0.005 THEN 1 ELSE 0 END) AS overdrawn
    FROM {S}.EV GROUP BY account_id
) s ON s.account_id = a.account_id;
