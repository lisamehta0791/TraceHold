-- ============================================================================
-- Stage 3a: trail edges (CF2 output) and the start of taint propagation.
-- Parameters: {S}, {DUST}
-- ============================================================================

DROP TABLE IF EXISTS {S}.EDGE_CARRY;
CREATE TABLE {S}.EDGE_CARRY AS
SELECT case_id, txn_id, SUM(c_pr) AS carried_pr, SUM(c_fifo) AS carried_fifo, SUM(c_lifo) AS carried_lifo,
       MIN(layer) AS layer
FROM (
    SELECT case_id, txn_id, amount AS c_pr, amount AS c_fifo, amount AS c_lifo, 1 AS layer FROM {S}.SEED
    UNION ALL
    SELECT case_id, txn_id, carried, 0, 0, layer FROM {S}.PR_OUT
    UNION ALL
    SELECT case_id, txn_id, 0, carried, 0, layer FROM {S}.FIFO_OUT
    UNION ALL
    SELECT case_id, txn_id, 0, 0, carried, layer FROM {S}.LIFO_OUT
) u
GROUP BY case_id, txn_id;

-- Flows below the dust threshold under a convention are not traced further
-- under that convention; they are reported as dust in the conservation check.
DROP TABLE IF EXISTS {S}.TRAIL_EDGES;
CREATE TABLE {S}.TRAIL_EDGES AS
SELECT e.case_id, e.txn_id, t.from_acct, t.to_acct, t.ts_epoch, t.amount, t.channel, t.txn_ref, e.layer,
       CASE WHEN e.carried_pr   >= {DUST} THEN e.carried_pr   ELSE 0 END AS carried_pr,
       CASE WHEN e.carried_fifo >= {DUST} THEN e.carried_fifo ELSE 0 END AS carried_fifo,
       CASE WHEN e.carried_lifo >= {DUST} THEN e.carried_lifo ELSE 0 END AS carried_lifo,
       CASE WHEN e.carried_pr   <  {DUST} THEN e.carried_pr   ELSE 0 END AS dust_pr,
       CASE WHEN e.carried_fifo <  {DUST} THEN e.carried_fifo ELSE 0 END AS dust_fifo,
       CASE WHEN e.carried_lifo <  {DUST} THEN e.carried_lifo ELSE 0 END AS dust_lifo,
       CASE WHEN t.to_acct = c.victim_account THEN 'RETURNED_TO_VICTIM'
            WHEN t.channel IN ('CASH_WD', 'WALLET') THEN 'CASH_OUT'
            WHEN t.channel = 'CHARGE' THEN 'CHARGES'
            WHEN t.to_acct IS NULL THEN 'CASH_OUT'
            WHEN o.account_id IS NULL THEN 'OUT_OF_SCOPE'
            ELSE 'INTERNAL' END AS terminal_state,
       COALESCE(sd.skew_adjusted, 0) AS skew_adjusted,
       CASE WHEN t.reversed > 0 THEN 1 ELSE 0 END AS partly_reversed
FROM {S}.EDGE_CARRY e
JOIN {S}.TXN_CLEAN t ON t.txn_id = e.txn_id
JOIN {S}.CASE_REF c ON c.case_id = e.case_id
LEFT JOIN {S}.OBS_ACC o ON o.account_id = t.to_acct
LEFT JOIN (SELECT txn_id, MAX(skew_adjusted) AS skew_adjusted FROM {S}.EV GROUP BY txn_id) sd ON sd.txn_id = e.txn_id;

-- Accounts that cannot be sized: a missing opening balance or a gap in the
-- records. Taint flows with material disputed funds to downstream accounts.
DROP TABLE IF EXISTS {S}.TAINT;
CREATE TABLE {S}.TAINT AS
SELECT e.case_id, e.to_acct AS account_id, MIN(e.ts_epoch) AS since_epoch
FROM {S}.TRAIL_EDGES e
JOIN {S}.ACC_FLAGS f ON f.account_id = e.to_acct
WHERE e.terminal_state = 'INTERNAL'
  AND GREATEST(e.carried_pr, e.carried_fifo, e.carried_lifo) >= {DUST}
  AND (f.missing_opening = 1 OR f.gap = 1)
GROUP BY e.case_id, e.to_acct;
