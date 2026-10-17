-- ============================================================================
-- CF5 scope-versus-evidence review and CF4 layer dilution.
-- Parameters: {S}, {FAST_MIN}, {SHARE_ALERT}
-- ============================================================================

-- Share of each account's inbound disputed funds (FIFO) moved onward quickly.
DROP TABLE IF EXISTS {S}.FAST_MOVE;
CREATE TABLE {S}.FAST_MOVE AS
SELECT i.case_id, i.account_id, i.inbound,
       COALESCE(o.fast_out, 0) AS fast_out
FROM (SELECT case_id, account_id, SUM(hi - lo) AS inbound FROM {S}.FIFO_SEG GROUP BY case_id, account_id) i
LEFT JOIN (
    SELECT case_id, account_id, SUM(off_hi - off_lo) AS fast_out
    FROM {S}.FIFO_PIECE
    WHERE ts_epoch - arr_epoch <= {FAST_MIN} * 60
    GROUP BY case_id, account_id
) o ON o.case_id = i.case_id AND o.account_id = i.account_id;

-- How many separate cases' trails reached each account within 30 days before
-- this case's reference time.
DROP TABLE IF EXISTS {S}.ACC_CASES;
CREATE TABLE {S}.ACC_CASES AS
SELECT h.case_id, h.account_id, COUNT(DISTINCT e.case_id) AS n_cases
FROM {S}.HOLDERS h
JOIN {S}.CASE_REF c ON c.case_id = h.case_id
JOIN {S}.TRAIL_EDGES e ON e.to_acct = h.account_id AND e.terminal_state = 'INTERNAL'
 AND e.ts_epoch BETWEEN c.ref_epoch - 30 * 86400 AND c.ref_epoch
 AND GREATEST(e.carried_pr, e.carried_fifo, e.carried_lifo) > 0
GROUP BY h.case_id, h.account_id;

DROP TABLE IF EXISTS {S}.REVIEW;
CREATE TABLE {S}.REVIEW AS
WITH t AS (
    SELECT t.request_id, r.case_id, t.account_id, t.requested_scope,
           CASE WHEN t.requested_scope = 'WHOLE_BALANCE' THEN GREATEST(CAST(s.balance_ref AS DOUBLE PRECISION), 0)
                ELSE CAST(t.requested_amount AS DOUBLE PRECISION) END AS requested,
           s.balance_ref, s.lower_amt, s.upper_amt, s.status, s.share_hi, s.layer
    FROM {S}.REQUEST_TARGETS t
    JOIN {S}.REQUESTS r ON r.request_id = t.request_id
    LEFT JOIN {S}.SIZING s ON s.case_id = r.case_id AND s.account_id = t.account_id
)
SELECT t.request_id, t.case_id, t.account_id, t.layer, t.requested_scope,
       CAST(t.requested AS DECIMAL(18,2)) AS requested_amount,
       t.balance_ref, t.lower_amt, t.upper_amt, t.status,
       CASE WHEN t.status IS NULL OR t.status = 'UNDETERMINABLE' OR t.requested IS NULL THEN 'CANNOT_DETERMINE'
            WHEN t.requested <= CAST(t.lower_amt AS DOUBLE PRECISION) + 0.005 THEN 'WITHIN_EVIDENCE'
            WHEN t.requested <= CAST(t.upper_amt AS DOUBLE PRECISION) + 0.005 THEN 'WITHIN_RANGE'
            ELSE 'EXCEEDS_EVIDENCE' END AS classification,
       CASE WHEN t.status IS NULL OR t.status = 'UNDETERMINABLE' OR CAST(t.upper_amt AS DOUBLE PRECISION) < 0.005 THEN NULL
            ELSE CAST(t.requested / CAST(t.upper_amt AS DOUBLE PRECISION) AS DECIMAL(18,4)) END AS ratio_to_upper,
       CAST(GREATEST(t.requested - COALESCE(CAST(t.upper_amt AS DOUBLE PRECISION), 0), 0) AS DECIMAL(18,2)) AS excess_over_upper,
       COALESCE(ac.n_cases, 0) AS cases_through_account,
       CASE WHEN fm.inbound > 0 THEN CAST(fm.fast_out / fm.inbound AS DECIMAL(9,6)) END AS share_moved_fast,
       CASE WHEN t.share_hi IS NULL THEN NULL ELSE CAST(1 - t.share_hi AS DECIMAL(9,6)) END AS commingling,
       CASE WHEN t.status = 'DETERMINED' THEN 1 ELSE 0 END AS separable
FROM t
LEFT JOIN {S}.ACC_CASES ac ON ac.case_id = t.case_id AND ac.account_id = t.account_id
LEFT JOIN {S}.FAST_MOVE fm ON fm.case_id = t.case_id AND fm.account_id = t.account_id;

-- CF4: traceable share summarised by layer, per case.
DROP TABLE IF EXISTS {S}.DILUTION;
CREATE TABLE {S}.DILUTION AS
SELECT s.case_id, s.layer, COUNT(*) AS n_accounts,
       AVG(CAST(s.retained_pr AS DOUBLE PRECISION) / CAST(s.balance_ref AS DOUBLE PRECISION)) AS share_pr,
       AVG(CAST(s.retained_fifo AS DOUBLE PRECISION) / CAST(s.balance_ref AS DOUBLE PRECISION)) AS share_fifo,
       SUM(CASE WHEN s.share_hi < {SHARE_ALERT} THEN 1 ELSE 0 END) AS below_threshold
FROM {S}.SIZING s
WHERE s.received = 1 AND s.status <> 'UNDETERMINABLE' AND s.balance_ref > 0.005 AND s.layer IS NOT NULL
GROUP BY s.case_id, s.layer;
