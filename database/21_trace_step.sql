-- ============================================================================
-- Stage 2b: one layer of trail expansion, all cases at once, all conventions.
-- Run repeatedly until PR_IN, FIFO_SEG and LIFO_SEG stop changing. Each pass
-- recomputes every outflow from the current state (set-based, no recursion),
-- so after n passes every time-respecting path of length n is resolved.
-- Parameters: {S}, {DUST}
-- ============================================================================

-- ---------------------------------------------------------------- pro-rata
DROP TABLE IF EXISTS {S}.PR_OUT;
CREATE TABLE {S}.PR_OUT AS
SELECT j.case_id, k.account_id, k.txn_id, k.ev_rank, k.ord_epoch AS ts_epoch, k.counterparty AS to_acct,
       k.channel,
       k.share * SUM(j.d * CASE WHEN k.lcum - k.lnf - j.lcum < -700 THEN 0.0
                                ELSE EXP(k.lcum - k.lnf - j.lcum) END) AS carried,
       MIN(j.layer) + 1 AS layer
FROM {S}.PR_IN j
JOIN {S}.CASE_REF c ON c.case_id = j.case_id
JOIN {S}.EV k ON k.account_id = j.account_id AND k.kind = 'D'
             AND k.ev_rank > j.ev_rank AND k.ord_epoch <= c.ref_epoch
GROUP BY j.case_id, k.account_id, k.txn_id, k.ev_rank, k.ord_epoch, k.counterparty, k.channel, k.share;

DROP TABLE IF EXISTS {S}.PR_IN_NEW;
CREATE TABLE {S}.PR_IN_NEW AS
SELECT case_id, account_id, txn_id, ev_rank, ts_epoch, lcum, d_gross, d, layer FROM {S}.PR_SEED
UNION ALL
SELECT o.case_id, r.account_id, r.txn_id, r.ev_rank, r.ord_epoch, r.lcum,
       o.carried, o.carried * (1 - r.absorbed_frac), o.layer
FROM {S}.PR_OUT o
JOIN {S}.CASE_REF c ON c.case_id = o.case_id
JOIN {S}.EV r ON r.txn_id = o.txn_id AND r.kind = 'C' AND r.account_id = o.to_acct
WHERE o.carried >= {DUST} AND o.to_acct <> c.victim_account;

-- ---------------------------------------------------------------- FIFO
DROP TABLE IF EXISTS {S}.FIFO_PIECE;
CREATE TABLE {S}.FIFO_PIECE AS
SELECT s.case_id, s.account_id, k.txn_id, k.ev_rank, k.ord_epoch AS ts_epoch, k.counterparty AS to_acct,
       k.channel, s.arr_epoch, s.layer,
       GREATEST(s.lo, k.cout_before) - k.cout_before AS off_lo,
       LEAST(s.hi, k.cout_before + k.amount) - k.cout_before AS off_hi
FROM {S}.FIFO_SEG s
JOIN {S}.CASE_REF c ON c.case_id = s.case_id
JOIN {S}.EV k ON k.account_id = s.account_id AND k.kind = 'D'
             AND k.ev_rank > s.arr_rank AND k.ord_epoch <= c.ref_epoch
             AND k.cout_before < s.hi AND k.cout_before + k.amount > s.lo;

DROP TABLE IF EXISTS {S}.FIFO_OUT;
CREATE TABLE {S}.FIFO_OUT AS
SELECT case_id, account_id, txn_id, MIN(ts_epoch) AS ts_epoch, MIN(to_acct) AS to_acct, MIN(channel) AS channel,
       SUM(off_hi - off_lo) AS carried, MIN(layer) + 1 AS layer
FROM {S}.FIFO_PIECE
GROUP BY case_id, account_id, txn_id;

DROP TABLE IF EXISTS {S}.FIFO_SEG_NEW;
CREATE TABLE {S}.FIFO_SEG_NEW AS
SELECT case_id, account_id, txn_id, arr_rank, arr_epoch, cout_arr, lo, hi, layer FROM {S}.FIFO_SEED
UNION ALL
SELECT p.case_id, r.account_id, r.txn_id, r.ev_rank, r.ord_epoch, r.cout_before,
       r.cin_before + p.off_lo, r.cin_before + p.off_hi, o.layer
FROM {S}.FIFO_PIECE p
JOIN {S}.FIFO_OUT o ON o.case_id = p.case_id AND o.txn_id = p.txn_id
JOIN {S}.CASE_REF c ON c.case_id = p.case_id
JOIN {S}.EV r ON r.txn_id = p.txn_id AND r.kind = 'C' AND r.account_id = p.to_acct
WHERE o.carried >= {DUST} AND p.to_acct <> c.victim_account;

-- ---------------------------------------------------------------- LIFO
DROP TABLE IF EXISTS {S}.LIFO_PIECE;
CREATE TABLE {S}.LIFO_PIECE AS
WITH w AS (
    SELECT s.case_id, s.account_id, s.arr_rank, s.lo, s.lo_eff, s.hi, s.layer, s.arr_epoch,
           e.ev_rank, e.kind, e.txn_id, e.ord_epoch, e.counterparty, e.channel, e.bal_after,
           MIN(e.bal_after) OVER (PARTITION BY s.case_id, s.account_id, s.arr_rank, s.lo ORDER BY e.ev_rank
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS runmin_prev
    FROM {S}.LIFO_SEG s
    JOIN {S}.CASE_REF c ON c.case_id = s.case_id
    JOIN {S}.EV e ON e.account_id = s.account_id AND e.ev_rank >= s.arr_rank AND e.ord_epoch <= c.ref_epoch
)
SELECT case_id, account_id, txn_id, ev_rank, ord_epoch AS ts_epoch, counterparty AS to_acct, channel,
       arr_epoch, layer,
       GREATEST(lo_eff, bal_after) - bal_after AS off_lo,
       LEAST(hi, runmin_prev) - bal_after AS off_hi
FROM w
WHERE kind = 'D' AND ev_rank > arr_rank
  AND LEAST(hi, runmin_prev) > GREATEST(lo_eff, bal_after) + 0.0000001;

DROP TABLE IF EXISTS {S}.LIFO_OUT;
CREATE TABLE {S}.LIFO_OUT AS
SELECT case_id, account_id, txn_id, MIN(ts_epoch) AS ts_epoch, MIN(to_acct) AS to_acct, MIN(channel) AS channel,
       SUM(off_hi - off_lo) AS carried, MIN(layer) + 1 AS layer
FROM {S}.LIFO_PIECE
GROUP BY case_id, account_id, txn_id;

DROP TABLE IF EXISTS {S}.LIFO_SEG_NEW;
CREATE TABLE {S}.LIFO_SEG_NEW AS
SELECT case_id, account_id, txn_id, arr_rank, arr_epoch, lo, lo_eff, hi, layer FROM {S}.LIFO_SEED
UNION ALL
SELECT p.case_id, r.account_id, r.txn_id, r.ev_rank, r.ord_epoch,
       r.bal_before + p.off_lo, GREATEST(r.bal_before + p.off_lo, 0), r.bal_before + p.off_hi, o.layer
FROM {S}.LIFO_PIECE p
JOIN {S}.LIFO_OUT o ON o.case_id = p.case_id AND o.txn_id = p.txn_id
JOIN {S}.CASE_REF c ON c.case_id = p.case_id
JOIN {S}.EV r ON r.txn_id = p.txn_id AND r.kind = 'C' AND r.account_id = p.to_acct
WHERE o.carried >= {DUST} AND p.to_acct <> c.victim_account;
