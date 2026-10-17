-- Stage 3b: one pass of taint propagation (repeat until stable). Parameters: {S}, {DUST}
DROP TABLE IF EXISTS {S}.TAINT_NEW;
CREATE TABLE {S}.TAINT_NEW AS
SELECT case_id, account_id, MIN(since_epoch) AS since_epoch
FROM (
    SELECT case_id, account_id, since_epoch FROM {S}.TAINT
    UNION ALL
    SELECT e.case_id, e.to_acct, e.ts_epoch
    FROM {S}.TRAIL_EDGES e
    JOIN {S}.TAINT t ON t.case_id = e.case_id AND t.account_id = e.from_acct AND e.ts_epoch >= t.since_epoch
    WHERE e.terminal_state = 'INTERNAL'
      AND GREATEST(e.carried_pr, e.carried_fifo, e.carried_lifo) >= {DUST}
) u
GROUP BY case_id, account_id;

DROP TABLE IF EXISTS {S}.TAINT;
CREATE TABLE {S}.TAINT AS SELECT * FROM {S}.TAINT_NEW;
