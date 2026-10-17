-- Cases in scope with their reference time. Parameters: {S}, {REF_EXPR}, {CASE_FILTER}
DROP TABLE IF EXISTS {S}.CASE_REF;
CREATE TABLE {S}.CASE_REF AS
SELECT c.case_id, c.case_ref, c.victim_account, CAST(c.reported_loss AS DOUBLE PRECISION) AS loss,
       c.fraud_epoch, {REF_EXPR} AS ref_epoch
FROM {S}.CASES c
WHERE {CASE_FILTER};
