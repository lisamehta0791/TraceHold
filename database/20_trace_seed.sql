-- ============================================================================
-- Stage 2a: seed the trail with the reported disputed transfers (layer 1).
--
-- Three allocation conventions are carried side by side:
--   PR    pro-rata. State: disputed credits (PR_IN). For a debit k after
--         credit j in the same account, the disputed amount still present
--         from j is  d_j * exp(L(k-1) - L(j)),  where L is the cumulative sum
--         of ln(1 - share) over the account's debits. A debit carries
--         share_k times the disputed amount present just before it.
--   FIFO  oldest funds leave first. State: disputed segments on the account's
--         cumulative-inflow axis (FIFO_SEG). A debit consumes the interval
--         [cout_before, cout_before + amount) of that axis.
--   LIFO  newest funds leave first. State: disputed segments on the balance
--         "level" axis (LIFO_SEG). A segment survives up to the running
--         minimum balance since it arrived; a debit consumes the levels
--         between its balance after and that running minimum.
-- ============================================================================

DROP TABLE IF EXISTS {S}.SEED;
CREATE TABLE {S}.SEED AS
SELECT d.case_id, t.txn_id, t.from_acct, t.to_acct, t.amount, t.ts_epoch, t.channel
FROM {S}.CASE_DISPUTED_TXNS d
JOIN {S}.CASE_REF c ON c.case_id = d.case_id
JOIN {S}.TXN_CLEAN t ON t.txn_id = d.txn_id;

DROP TABLE IF EXISTS {S}.PR_SEED;
CREATE TABLE {S}.PR_SEED AS
SELECT s.case_id, r.account_id, r.txn_id, r.ev_rank, r.ord_epoch AS ts_epoch, r.lcum,
       s.amount AS d_gross, s.amount * (1 - r.absorbed_frac) AS d, 1 AS layer
FROM {S}.SEED s
JOIN {S}.CASE_REF c ON c.case_id = s.case_id
JOIN {S}.EV r ON r.txn_id = s.txn_id AND r.kind = 'C' AND r.account_id = s.to_acct
WHERE r.ord_epoch <= c.ref_epoch;

DROP TABLE IF EXISTS {S}.FIFO_SEED;
CREATE TABLE {S}.FIFO_SEED AS
SELECT s.case_id, r.account_id, r.txn_id, r.ev_rank AS arr_rank, r.ord_epoch AS arr_epoch,
       r.cout_before AS cout_arr, r.cin_before AS lo, r.cin_before + s.amount AS hi, 1 AS layer
FROM {S}.SEED s
JOIN {S}.CASE_REF c ON c.case_id = s.case_id
JOIN {S}.EV r ON r.txn_id = s.txn_id AND r.kind = 'C' AND r.account_id = s.to_acct
WHERE r.ord_epoch <= c.ref_epoch;

DROP TABLE IF EXISTS {S}.LIFO_SEED;
CREATE TABLE {S}.LIFO_SEED AS
SELECT s.case_id, r.account_id, r.txn_id, r.ev_rank AS arr_rank, r.ord_epoch AS arr_epoch,
       r.bal_before AS lo, GREATEST(r.bal_before, 0) AS lo_eff, r.bal_before + s.amount AS hi, 1 AS layer
FROM {S}.SEED s
JOIN {S}.CASE_REF c ON c.case_id = s.case_id
JOIN {S}.EV r ON r.txn_id = s.txn_id AND r.kind = 'C' AND r.account_id = s.to_acct
WHERE r.ord_epoch <= c.ref_epoch;

DROP TABLE IF EXISTS {S}.PR_IN;
CREATE TABLE {S}.PR_IN AS SELECT * FROM {S}.PR_SEED;
DROP TABLE IF EXISTS {S}.FIFO_SEG;
CREATE TABLE {S}.FIFO_SEG AS SELECT * FROM {S}.FIFO_SEED;
DROP TABLE IF EXISTS {S}.LIFO_SEG;
CREATE TABLE {S}.LIFO_SEG AS SELECT * FROM {S}.LIFO_SEED;
