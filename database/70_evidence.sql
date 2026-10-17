-- ============================================================================
-- CF7 evidence items: every sized figure with the transaction records it rests
-- on (credits into and debits out of the account carrying the case's funds).
-- Exasol-specific (GROUP_CONCAT). Parameters: {S}
-- ============================================================================

DROP TABLE IF EXISTS {S}.EVIDENCE_ITEMS;
CREATE TABLE {S}.EVIDENCE_ITEMS AS
WITH src AS (
    SELECT case_id, to_acct AS account_id, txn_id, ts_epoch, 'IN' AS direction FROM {S}.TRAIL_EDGES
    WHERE GREATEST(carried_pr, carried_fifo, carried_lifo) > 0
    UNION ALL
    SELECT case_id, from_acct, txn_id, ts_epoch, 'OUT' FROM {S}.TRAIL_EDGES
    WHERE GREATEST(carried_pr, carried_fifo, carried_lifo) > 0
), agg AS (
    SELECT case_id, account_id,
           GROUP_CONCAT(CASE WHEN direction = 'IN' THEN txn_id END ORDER BY ts_epoch, txn_id SEPARATOR ',') AS in_txns,
           GROUP_CONCAT(CASE WHEN direction = 'OUT' THEN txn_id END ORDER BY ts_epoch, txn_id SEPARATOR ',') AS out_txns,
           COUNT(*) AS n_records
    FROM src GROUP BY case_id, account_id
)
SELECT s.case_id, s.account_id, f.figure,
       CASE f.figure WHEN 'BALANCE_REF' THEN s.balance_ref WHEN 'RETAINED_PR' THEN s.retained_pr
                     WHEN 'RETAINED_FIFO' THEN s.retained_fifo ELSE s.retained_lifo END AS figure_value,
       a.in_txns, a.out_txns, COALESCE(a.n_records, 0) AS n_records,
       CASE f.figure WHEN 'BALANCE_REF' THEN 'Opening balance and every posting up to the reference time'
                     WHEN 'RETAINED_PR' THEN 'Pro-rata: each debit carries the account''s disputed proportion'
                     WHEN 'RETAINED_FIFO' THEN 'FIFO: oldest funds leave first'
                     ELSE 'LIFO (bounding case): newest funds leave first' END AS assumption
FROM {S}.SIZING s
CROSS JOIN (SELECT 'BALANCE_REF' AS figure UNION ALL SELECT 'RETAINED_PR' UNION ALL SELECT 'RETAINED_FIFO'
            UNION ALL SELECT 'RETAINED_LIFO') f
LEFT JOIN agg a ON a.case_id = s.case_id AND a.account_id = s.account_id;
