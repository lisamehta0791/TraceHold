-- ============================================================================
-- Stage 3c: per-account sizing at the reference time (CF3), statuses (CF6),
-- conservation check, out-of-scope destinations (CF8 input).
-- Parameters: {S}, {DUST}
-- ============================================================================

DROP TABLE IF EXISTS {S}.HOLDERS;
CREATE TABLE {S}.HOLDERS AS
SELECT case_id, account_id, MIN(layer) AS layer, MAX(received) AS received
FROM (
    SELECT case_id, account_id, layer, 1 AS received FROM {S}.PR_IN
    UNION ALL SELECT case_id, account_id, layer, 1 FROM {S}.FIFO_SEG
    UNION ALL SELECT case_id, account_id, layer, 1 FROM {S}.LIFO_SEG
    UNION ALL
    SELECT r.case_id, t.account_id, CAST(NULL AS INTEGER), 0
    FROM {S}.REQUEST_TARGETS t
    JOIN {S}.REQUESTS r ON r.request_id = t.request_id
    JOIN {S}.OBS_ACC o ON o.account_id = t.account_id
) u
GROUP BY case_id, account_id;

DROP TABLE IF EXISTS {S}.REF_STATE;
CREATE TABLE {S}.REF_STATE AS
SELECT p.case_id, p.account_id, p.ref_rank,
       COALESCE(e.bal_after, a.opening) AS balance_ref,
       COALESCE(e.lcum, 0) AS lcum_ref,
       COALESCE(e.cout_before + CASE WHEN e.kind = 'D' THEN e.amount ELSE 0 END, GREATEST(-a.opening, 0)) AS cout_ref
FROM (
    SELECT h.case_id, h.account_id, MAX(e.ev_rank) AS ref_rank
    FROM {S}.HOLDERS h
    JOIN {S}.CASE_REF c ON c.case_id = h.case_id
    LEFT JOIN {S}.EV e ON e.account_id = h.account_id AND e.ord_epoch <= c.ref_epoch
    GROUP BY h.case_id, h.account_id
) p
JOIN {S}.OBS_ACC a ON a.account_id = p.account_id
LEFT JOIN {S}.EV e ON e.account_id = p.account_id AND e.ev_rank = p.ref_rank;

DROP TABLE IF EXISTS {S}.RET_PR;
CREATE TABLE {S}.RET_PR AS
SELECT j.case_id, j.account_id,
       SUM(j.d * CASE WHEN s.lcum_ref - j.lcum < -700 THEN 0.0 ELSE EXP(s.lcum_ref - j.lcum) END) AS retained,
       SUM(j.d_gross - j.d) AS absorbed,
       SUM(j.d_gross) AS inbound
FROM {S}.PR_IN j
JOIN {S}.REF_STATE s ON s.case_id = j.case_id AND s.account_id = j.account_id
GROUP BY j.case_id, j.account_id;

DROP TABLE IF EXISTS {S}.RET_FIFO;
CREATE TABLE {S}.RET_FIFO AS
SELECT f.case_id, f.account_id,
       SUM(GREATEST(0, f.hi - GREATEST(f.lo, s.cout_ref))) AS retained,
       SUM(GREATEST(0, LEAST(f.hi, f.cout_arr) - f.lo)) AS absorbed,
       SUM(f.hi - f.lo) AS inbound
FROM {S}.FIFO_SEG f
JOIN {S}.REF_STATE s ON s.case_id = f.case_id AND s.account_id = f.account_id
GROUP BY f.case_id, f.account_id;

DROP TABLE IF EXISTS {S}.RET_LIFO;
CREATE TABLE {S}.RET_LIFO AS
SELECT m.case_id, m.account_id,
       SUM(GREATEST(0, LEAST(m.hi, m.runmin) - m.lo_eff)) AS retained,
       SUM(GREATEST(0, LEAST(m.hi, 0) - m.lo)) AS absorbed,
       SUM(m.hi - m.lo) AS inbound
FROM (
    SELECT l.case_id, l.account_id, l.arr_rank, l.lo, l.lo_eff, l.hi, MIN(e.bal_after) AS runmin
    FROM {S}.LIFO_SEG l
    JOIN {S}.REF_STATE s ON s.case_id = l.case_id AND s.account_id = l.account_id
    JOIN {S}.EV e ON e.account_id = l.account_id AND e.ev_rank >= l.arr_rank AND e.ev_rank <= s.ref_rank
    GROUP BY l.case_id, l.account_id, l.arr_rank, l.lo, l.lo_eff, l.hi
) m
GROUP BY m.case_id, m.account_id;

-- ---------------------------------------------------------------- sizing
DROP TABLE IF EXISTS {S}.SIZING;
CREATE TABLE {S}.SIZING AS
WITH base AS (
    SELECT h.case_id, h.account_id, h.layer, h.received, s.balance_ref,
           COALESCE(p.retained, 0) AS r_pr, COALESCE(f.retained, 0) AS r_fifo, COALESCE(l.retained, 0) AS r_lifo,
           CASE WHEN t.account_id IS NULL THEN 0 ELSE 1 END AS tainted,
           af.missing_opening, af.gap, af.skew_fixes, af.overdrawn
    FROM {S}.HOLDERS h
    JOIN {S}.REF_STATE s ON s.case_id = h.case_id AND s.account_id = h.account_id
    JOIN {S}.ACC_FLAGS af ON af.account_id = h.account_id
    LEFT JOIN {S}.RET_PR p ON p.case_id = h.case_id AND p.account_id = h.account_id
    LEFT JOIN {S}.RET_FIFO f ON f.case_id = h.case_id AND f.account_id = h.account_id
    LEFT JOIN {S}.RET_LIFO l ON l.case_id = h.case_id AND l.account_id = h.account_id
    LEFT JOIN {S}.TAINT t ON t.case_id = h.case_id AND t.account_id = h.account_id
), st AS (
    SELECT b.*,
           CASE WHEN b.tainted = 1 OR (b.received = 0 AND (b.missing_opening = 1 OR b.gap = 1)) THEN 'UNDETERMINABLE'
                WHEN ABS(b.r_pr - b.r_fifo) <= 0.01 THEN 'DETERMINED'
                ELSE 'RANGE' END AS status,
           LEAST(b.r_pr, b.r_fifo) AS lo2, GREATEST(b.r_pr, b.r_fifo) AS hi2,
           LEAST(b.r_pr, b.r_fifo, b.r_lifo) AS lo3, GREATEST(b.r_pr, b.r_fifo, b.r_lifo) AS hi3
    FROM base b
)
SELECT case_id, account_id, layer, received,
       CAST(balance_ref AS DECIMAL(18,2)) AS balance_ref,
       CAST(r_pr AS DECIMAL(18,2)) AS retained_pr,
       CAST(r_fifo AS DECIMAL(18,2)) AS retained_fifo,
       CAST(r_lifo AS DECIMAL(18,2)) AS retained_lifo,
       CASE WHEN status = 'UNDETERMINABLE' THEN NULL ELSE CAST(lo2 AS DECIMAL(18,2)) END AS lower_amt,
       CASE WHEN status = 'UNDETERMINABLE' THEN NULL ELSE CAST(hi2 AS DECIMAL(18,2)) END AS upper_amt,
       CASE WHEN status = 'UNDETERMINABLE' THEN NULL ELSE CAST(lo3 AS DECIMAL(18,2)) END AS lower_ext,
       CASE WHEN status = 'UNDETERMINABLE' THEN NULL ELSE CAST(hi3 AS DECIMAL(18,2)) END AS upper_ext,
       CASE WHEN status = 'UNDETERMINABLE' OR balance_ref <= 0.005 THEN NULL
            ELSE CAST(LEAST(1.0, lo2 / balance_ref) AS DECIMAL(9,6)) END AS share_lo,
       CASE WHEN status = 'UNDETERMINABLE' OR balance_ref <= 0.005 THEN NULL
            ELSE CAST(LEAST(1.0, hi2 / balance_ref) AS DECIMAL(9,6)) END AS share_hi,
       CASE WHEN status = 'UNDETERMINABLE' OR hi3 < 0.005 THEN NULL
            ELSE CAST((hi3 - lo3) / hi3 AS DECIMAL(9,6)) END AS sensitivity,
       status,
       CONCAT(
         CASE WHEN missing_opening = 1 THEN 'MISSING_OPENING;' ELSE '' END,
         CASE WHEN gap = 1 THEN 'RECORDS_GAP;' ELSE '' END,
         CASE WHEN tainted = 1 AND missing_opening = 0 AND gap = 0 THEN 'UPSTREAM_UNDETERMINABLE;' ELSE '' END,
         CASE WHEN status = 'RANGE' THEN 'CONVENTIONS_DISAGREE;' ELSE '' END,
         CASE WHEN skew_fixes > 0 THEN 'SKEW_ADJUSTED;' ELSE '' END,
         CASE WHEN overdrawn > 0 THEN 'OVERDRAWN;' ELSE '' END,
         CASE WHEN received = 0 THEN 'NO_DISPUTED_FUNDS_RECEIVED;' ELSE '' END
       ) AS reason_codes
FROM st;

-- Destinations outside the available records, with the amount in transit.
DROP TABLE IF EXISTS {S}.OUT_OF_SCOPE;
CREATE TABLE {S}.OUT_OF_SCOPE AS
SELECT case_id, txn_id, from_acct, to_acct, ts_epoch, amount, channel, txn_ref, layer,
       carried_pr, carried_fifo, carried_lifo
FROM {S}.TRAIL_EDGES
WHERE terminal_state = 'OUT_OF_SCOPE'
  AND GREATEST(carried_pr, carried_fifo, carried_lifo) >= {DUST};

-- ---------------------------------------------------------------- conservation
DROP TABLE IF EXISTS {S}.CONSERVATION;
CREATE TABLE {S}.CONSERVATION AS
WITH seeded AS (SELECT case_id, SUM(amount) AS seeded FROM {S}.SEED GROUP BY case_id),
ex AS (
    SELECT case_id,
           SUM(CASE WHEN terminal_state <> 'INTERNAL' THEN carried_pr ELSE 0 END) AS ex_pr,
           SUM(CASE WHEN terminal_state <> 'INTERNAL' THEN carried_fifo ELSE 0 END) AS ex_fifo,
           SUM(CASE WHEN terminal_state <> 'INTERNAL' THEN carried_lifo ELSE 0 END) AS ex_lifo,
           SUM(dust_pr) AS du_pr, SUM(dust_fifo) AS du_fifo, SUM(dust_lifo) AS du_lifo
    FROM {S}.TRAIL_EDGES GROUP BY case_id
),
rt AS (
    SELECT case_id, SUM(retained) AS ret, SUM(absorbed) AS abs_amt, 'PR' AS convention FROM {S}.RET_PR GROUP BY case_id
    UNION ALL
    SELECT case_id, SUM(retained), SUM(absorbed), 'FIFO' FROM {S}.RET_FIFO GROUP BY case_id
    UNION ALL
    SELECT case_id, SUM(retained), SUM(absorbed), 'LIFO' FROM {S}.RET_LIFO GROUP BY case_id
),
conv AS (
    SELECT 'PR' AS convention UNION ALL SELECT 'FIFO' UNION ALL SELECT 'LIFO'
),
grid AS (
    SELECT c.case_id, c.loss, v.convention, COALESCE(s.seeded, 0) AS seeded
    FROM {S}.CASE_REF c CROSS JOIN conv v
    LEFT JOIN seeded s ON s.case_id = c.case_id
)
SELECT x.*, x.seeded - (x.retained + x.exited + x.dust + x.absorbed) AS difference,
       CASE WHEN ABS(x.seeded - (x.retained + x.exited + x.dust + x.absorbed)) <= 0.01
             AND ABS(x.seeded - x.loss) <= 0.01 THEN 1 ELSE 0 END AS passed
FROM (
SELECT g.case_id, g.convention, g.loss, g.seeded,
       COALESCE(r.ret, 0) AS retained,
       COALESCE(CASE g.convention WHEN 'PR' THEN e.ex_pr WHEN 'FIFO' THEN e.ex_fifo ELSE e.ex_lifo END, 0) AS exited,
       COALESCE(CASE g.convention WHEN 'PR' THEN e.du_pr WHEN 'FIFO' THEN e.du_fifo ELSE e.du_lifo END, 0) AS dust,
       COALESCE(r.abs_amt, 0) AS absorbed
FROM grid g
LEFT JOIN rt r ON r.case_id = g.case_id AND r.convention = g.convention
LEFT JOIN ex e ON e.case_id = g.case_id
) x;
