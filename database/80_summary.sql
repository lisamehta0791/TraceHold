-- ============================================================================
-- Case-level summary used by the case explorer and overview. Parameters: {S}
-- Duplicate requests are excluded from totals so amounts are not double counted.
-- ============================================================================
DROP TABLE IF EXISTS {S}.CASE_SUMMARY;
CREATE TABLE {S}.CASE_SUMMARY AS
WITH dup AS (SELECT DISTINCT request_id FROM {S}.REQ_FINDINGS WHERE item_code = 'DUPLICATE_REQUEST'),
prim AS (SELECT case_id, MIN(request_id) AS request_id FROM {S}.REQUESTS GROUP BY case_id),
rva AS (
    SELECT v.case_id,
           SUM(v.requested_amount) AS requested_total,
           SUM(v.lower_amt) AS supported_lower,
           SUM(v.upper_amt) AS supported_upper,
           SUM(GREATEST(v.balance_ref, 0)) AS whole_balance,
           SUM(v.excess_over_upper) AS excess,
           MAX(CASE v.classification WHEN 'EXCEEDS_EVIDENCE' THEN 4 WHEN 'CANNOT_DETERMINE' THEN 3
                                     WHEN 'WITHIN_RANGE' THEN 2 ELSE 1 END) AS worst_rank,
           COUNT(*) AS n_targets,
           SUM(CASE WHEN v.classification = 'EXCEEDS_EVIDENCE' THEN 1 ELSE 0 END) AS n_exceeds
    FROM {S}.REVIEW v
    WHERE v.request_id NOT IN (SELECT request_id FROM dup)
    GROUP BY v.case_id
),
sz AS (SELECT case_id, SUM(received) AS n_accounts, MAX(layer) AS max_layer,
              SUM(CASE WHEN status = 'UNDETERMINABLE' THEN 1 ELSE 0 END) AS n_undeterminable
       FROM {S}.SIZING GROUP BY case_id),
oos AS (SELECT case_id, COUNT(*) AS n_oos FROM {S}.OUT_OF_SCOPE GROUP BY case_id),
cons AS (SELECT case_id, MIN(passed) AS conservation_ok FROM {S}.CONSERVATION GROUP BY case_id)
SELECT c.case_id, c.case_ref, c.victim_account, c.loss, c.fraud_epoch, c.ref_epoch,
       p.request_id, rs.status AS request_status,
       COALESCE(sz.n_accounts, 0) AS n_accounts, COALESCE(sz.max_layer, 0) AS max_layer,
       COALESCE(sz.n_undeterminable, 0) AS n_undeterminable,
       COALESCE(rva.requested_total, 0) AS requested_total,
       COALESCE(rva.supported_lower, 0) AS supported_lower,
       COALESCE(rva.supported_upper, 0) AS supported_upper,
       COALESCE(rva.whole_balance, 0) AS whole_balance,
       COALESCE(rva.excess, 0) AS excess,
       COALESCE(rva.n_targets, 0) AS n_targets,
       COALESCE(rva.n_exceeds, 0) AS n_exceeds,
       CASE rva.worst_rank WHEN 4 THEN 'EXCEEDS_EVIDENCE' WHEN 3 THEN 'CANNOT_DETERMINE'
                           WHEN 2 THEN 'WITHIN_RANGE' WHEN 1 THEN 'WITHIN_EVIDENCE' END AS worst_classification,
       COALESCE(oos.n_oos, 0) AS n_out_of_scope,
       COALESCE(cons.conservation_ok, 0) AS conservation_ok
FROM {S}.CASE_REF c
LEFT JOIN prim p ON p.case_id = c.case_id
LEFT JOIN {S}.REQ_STATUS rs ON rs.request_id = p.request_id
LEFT JOIN rva ON rva.case_id = c.case_id
LEFT JOIN sz ON sz.case_id = c.case_id
LEFT JOIN oos ON oos.case_id = c.case_id
LEFT JOIN cons ON cons.case_id = c.case_id;
