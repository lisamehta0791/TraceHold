-- ============================================================================
-- Additional features computed in the database.
--   AF1 lien review queue (rules from the 2 Jan 2026 procedure as reported by
--       LiveLaw; configurable, to be checked against the primary text)
--   AF4 speed of movement (share of disputed funds still inside observable
--       accounts by minutes since the fraud)
-- Parameters: {S}, {AS_OF}, {LIEN_THRESHOLD}, {REVIEW_DAYS}
-- ============================================================================

DROP TABLE IF EXISTS {S}.LIEN_REVIEW;
CREATE TABLE {S}.LIEN_REVIEW AS
WITH b AS (
    SELECT r.restraint_id, r.account_id, r.case_id, r.request_id, r.restraint_type,
           CAST(r.held_amount AS DOUBLE PRECISION) AS held, r.start_date, r.last_update_date,
           r.closure_status, r.released_date, r.issuing_authority,
           s.lower_amt, s.upper_amt, s.status,
           CASE WHEN c.loss < {LIEN_THRESHOLD} THEN 'UNDER_50K' ELSE 'OVER_50K' END AS band,
           COALESCE(r.released_date, DATE '{AS_OF}') - r.start_date AS days_held,
           DATE '{AS_OF}' - COALESCE(r.last_update_date, r.start_date) AS days_since_update,
           CASE WHEN r.released_date IS NULL THEN 1 ELSE 0 END AS active
    FROM {S}.RESTRAINTS r
    JOIN {S}.CASE_REF c ON c.case_id = r.case_id
    LEFT JOIN {S}.SIZING s ON s.case_id = r.case_id AND s.account_id = r.account_id
), f AS (
    SELECT b.*,
           CASE WHEN b.status IS NULL OR b.status = 'UNDETERMINABLE' THEN NULL
                WHEN CAST(b.upper_amt AS DOUBLE PRECISION) < 0.005 THEN NULL
                ELSE b.held / CAST(b.upper_amt AS DOUBLE PRECISION) END AS over_hold_ratio,
           CASE WHEN b.active = 1 AND b.status IS NOT NULL AND b.status <> 'UNDETERMINABLE'
                 AND b.held > COALESCE(CAST(b.upper_amt AS DOUBLE PRECISION), 0) + 1 THEN 1 ELSE 0 END AS f_over_hold,
           CASE WHEN b.active = 1 AND b.closure_status IN ('CLEAN_CHIT', 'CLOSURE_REPORT') THEN 1 ELSE 0 END AS f_closed_still_held,
           CASE WHEN b.active = 1 AND b.band = 'UNDER_50K' AND b.days_held > 90 THEN 1 ELSE 0 END AS f_past_90,
           CASE WHEN b.active = 1 AND b.band = 'OVER_50K' AND b.days_held > {REVIEW_DAYS} THEN 1 ELSE 0 END AS f_past_review,
           CASE WHEN b.active = 1 AND b.days_since_update >= 15 THEN 1 ELSE 0 END AS f_escalate,
           CASE WHEN b.status = 'UNDETERMINABLE' OR b.status IS NULL THEN 1 ELSE 0 END AS f_cannot_size
    FROM b
)
SELECT f.restraint_id, f.account_id, f.case_id, f.request_id, f.restraint_type,
       CAST(f.held AS DECIMAL(18,2)) AS held_amount, f.start_date, f.last_update_date, f.closure_status,
       f.released_date, f.issuing_authority, f.lower_amt, f.upper_amt, f.status, f.band, f.days_held,
       f.days_since_update, f.active,
       CAST(f.over_hold_ratio AS DECIMAL(18,4)) AS over_hold_ratio,
       CASE WHEN f.band = 'UNDER_50K' AND f.active = 1 THEN 90 - f.days_held END AS days_to_90,
       COALESCE(f.last_update_date, f.start_date) + 15 AS escalation_date,
       f.f_over_hold, f.f_closed_still_held, f.f_past_90, f.f_past_review, f.f_escalate, f.f_cannot_size,
       -- Review priority of the restraint (not of any person): a fixed,
       -- disclosed weighting of the facts above.
       CAST(f.active * (
           0.35 * CASE WHEN f.f_over_hold = 0 THEN 0
                       WHEN f.over_hold_ratio IS NULL THEN 1
                       ELSE LEAST(1.0, LN(GREATEST(f.over_hold_ratio, 1.0)) / LN(100.0)) END
         + 0.25 * f.f_closed_still_held
         + 0.20 * LEAST(1.0, f.days_held / 120.0)
         + 0.10 * GREATEST(f.f_past_90, f.f_past_review)
         + 0.10 * f.f_escalate) AS DECIMAL(9,4)) AS priority
FROM f;

-- AF4: disputed funds still inside observable accounts, by minutes since fraud.
DROP TABLE IF EXISTS {S}.MIN_GRID;
CREATE TABLE {S}.MIN_GRID AS
SELECT 0 AS minutes UNION ALL SELECT 5 UNION ALL SELECT 10 UNION ALL SELECT 15 UNION ALL SELECT 20
UNION ALL SELECT 30 UNION ALL SELECT 45 UNION ALL SELECT 60 UNION ALL SELECT 90 UNION ALL SELECT 120
UNION ALL SELECT 180 UNION ALL SELECT 240 UNION ALL SELECT 360 UNION ALL SELECT 480 UNION ALL SELECT 720
UNION ALL SELECT 1080 UNION ALL SELECT 1440 UNION ALL SELECT 2160 UNION ALL SELECT 2880;

DROP TABLE IF EXISTS {S}.SPEED;
CREATE TABLE {S}.SPEED AS
SELECT c.case_id, g.minutes,
       1 - COALESCE(SUM(CASE WHEN e.ts_epoch - c.fraud_epoch <= g.minutes * 60 THEN e.carried_pr END), 0) / c.loss AS inside_pr,
       1 - COALESCE(SUM(CASE WHEN e.ts_epoch - c.fraud_epoch <= g.minutes * 60 THEN e.carried_fifo END), 0) / c.loss AS inside_fifo
FROM {S}.CASE_REF c
CROSS JOIN {S}.MIN_GRID g
LEFT JOIN {S}.TRAIL_EDGES e ON e.case_id = c.case_id AND e.terminal_state <> 'INTERNAL'
WHERE g.minutes * 60 <= c.ref_epoch - c.fraud_epoch AND c.loss > 0
GROUP BY c.case_id, g.minutes, c.loss;
