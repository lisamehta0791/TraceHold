-- ============================================================================
-- CF1: request completeness and consistency.
-- Parameters: {S}, {MISSING_SQL} (generated from CHECKLIST_ITEMS)
-- ============================================================================

DROP TABLE IF EXISTS {S}.REQ_FINDINGS;
CREATE TABLE {S}.REQ_FINDINGS AS
SELECT request_id, CAST(NULL AS VARCHAR(20)) AS account_id, CAST(item_code AS VARCHAR(30)) AS item_code,
       CAST(label AS VARCHAR(100)) AS label, CAST(kind AS VARCHAR(10)) AS kind, CAST(detail AS VARCHAR(400)) AS detail
FROM ({MISSING_SQL}) m;

-- Quoted disputed transaction does not exist.
INSERT INTO {S}.REQ_FINDINGS
SELECT r.request_id, NULL, 'TXN_NOT_FOUND', 'Disputed transaction', 'CONFLICT',
       CONCAT('Quoted transaction ', r.quoted_txn_id, ' is not in the records')
FROM {S}.REQUESTS r
WHERE r.quoted_txn_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM {S}.TRANSACTIONS t WHERE t.txn_id = r.quoted_txn_id);

-- Quoted transaction exists but is not one the victim reported for this case.
INSERT INTO {S}.REQ_FINDINGS
SELECT r.request_id, NULL, 'TXN_NOT_DISPUTED', 'Disputed transaction', 'CONFLICT',
       CONCAT('Quoted transaction ', r.quoted_txn_id, ' is not a reported disputed transfer of this case')
FROM {S}.REQUESTS r
WHERE r.quoted_txn_id IS NOT NULL
  AND EXISTS (SELECT 1 FROM {S}.TRANSACTIONS t WHERE t.txn_id = r.quoted_txn_id)
  AND NOT EXISTS (SELECT 1 FROM {S}.CASE_DISPUTED_TXNS d WHERE d.case_id = r.case_id AND d.txn_id = r.quoted_txn_id);

-- Stated amount against the reported disputed transfers (including a unit slip).
INSERT INTO {S}.REQ_FINDINGS
SELECT r.request_id, NULL,
       CASE WHEN ABS(CAST(r.stated_amount AS DOUBLE PRECISION) - 100 * s.amt) <= 1 THEN 'AMOUNT_UNIT' ELSE 'AMOUNT_MISMATCH' END,
       'Disputed amount', 'CONFLICT',
       CASE WHEN ABS(CAST(r.stated_amount AS DOUBLE PRECISION) - 100 * s.amt) <= 1
            THEN CONCAT('Stated amount ', CAST(r.stated_amount AS VARCHAR(30)), ' is 100 times the recorded disputed amount ',
                        CAST(CAST(s.amt AS DECIMAL(18,2)) AS VARCHAR(30)), ' (paise quoted as rupees?)')
            ELSE CONCAT('Stated amount ', CAST(r.stated_amount AS VARCHAR(30)), ' differs from the recorded disputed amount ',
                        CAST(CAST(s.amt AS DECIMAL(18,2)) AS VARCHAR(30))) END
FROM {S}.REQUESTS r
JOIN (SELECT d.case_id, SUM(CAST(t.amount AS DOUBLE PRECISION)) AS amt
      FROM {S}.CASE_DISPUTED_TXNS d JOIN {S}.TRANSACTIONS t ON t.txn_id = d.txn_id
      GROUP BY d.case_id) s ON s.case_id = r.case_id
WHERE r.stated_amount IS NOT NULL
  AND ABS(CAST(r.stated_amount AS DOUBLE PRECISION) - s.amt) > 0.01;

-- Case reference that belongs to a different case.
INSERT INTO {S}.REQ_FINDINGS
SELECT r.request_id, NULL, 'REUSED_REFERENCE', 'FIR / crime / NCRP / CFCFRMS reference', 'CONFLICT',
       CONCAT('Reference ', r.case_reference, ' belongs to another case',
              CASE WHEN o.case_id IS NULL THEN '' ELSE CONCAT(' (case ', CAST(o.case_id AS VARCHAR(12)), ')') END)
FROM {S}.REQUESTS r
JOIN {S}.CASES c ON c.case_id = r.case_id
LEFT JOIN {S}.CASES o ON o.case_ref = r.case_reference
WHERE r.case_reference IS NOT NULL AND r.case_reference <> c.case_ref;

-- Duplicate request: an earlier request for the same case, action and targets.
INSERT INTO {S}.REQ_FINDINGS
WITH tc AS (SELECT request_id, COUNT(*) AS n FROM {S}.REQUEST_TARGETS GROUP BY request_id),
pairs AS (
    SELECT a.request_id AS first_id, b.request_id AS dup_id
    FROM {S}.REQUESTS a
    JOIN {S}.REQUESTS b ON a.case_id = b.case_id
     AND (a.received_epoch < b.received_epoch OR (a.received_epoch = b.received_epoch AND a.request_id < b.request_id))
     AND COALESCE(a.action_type, '-') = COALESCE(b.action_type, '-')
),
tmatch AS (
    SELECT p.first_id, p.dup_id, COUNT(*) AS m
    FROM pairs p
    JOIN {S}.REQUEST_TARGETS x ON x.request_id = p.dup_id
    JOIN {S}.REQUEST_TARGETS y ON y.request_id = p.first_id AND y.account_id = x.account_id
    GROUP BY p.first_id, p.dup_id
)
SELECT m.dup_id, NULL, 'DUPLICATE_REQUEST', 'Duplicate request', 'CONFLICT',
       CONCAT('Duplicates request ', CAST(MIN(m.first_id) AS VARCHAR(12)), ' (same case, action and accounts)')
FROM tmatch m
JOIN tc ta ON ta.request_id = m.first_id
JOIN tc tb ON tb.request_id = m.dup_id
WHERE m.m = ta.n AND m.m = tb.n
GROUP BY m.dup_id;

-- Target account not in the records.
INSERT INTO {S}.REQ_FINDINGS
SELECT t.request_id, t.account_id, 'TARGET_NOT_FOUND', 'Account details', 'CONFLICT',
       CONCAT('Account ', t.account_id, ' is not in the records')
FROM {S}.REQUEST_TARGETS t
WHERE NOT EXISTS (SELECT 1 FROM {S}.ACCOUNTS a WHERE a.account_id = t.account_id);

-- Target account is not a party to the transaction quoted for it.
INSERT INTO {S}.REQ_FINDINGS
SELECT t.request_id, t.account_id, 'TARGET_MISMATCH', 'Account and transaction details', 'CONFLICT',
       CONCAT('Account ', t.account_id, ' is not a party to the quoted transaction ', t.quoted_txn_id)
FROM {S}.REQUEST_TARGETS t
JOIN {S}.TRANSACTIONS x ON x.txn_id = t.quoted_txn_id
WHERE COALESCE(x.to_acct, '-') <> t.account_id AND COALESCE(x.from_acct, '-') <> t.account_id;

INSERT INTO {S}.REQ_FINDINGS
SELECT t.request_id, t.account_id, 'TARGET_TXN_NOT_FOUND', 'Account and transaction details', 'CONFLICT',
       CONCAT('Transaction ', t.quoted_txn_id, ' quoted for account ', t.account_id, ' is not in the records')
FROM {S}.REQUEST_TARGETS t
WHERE t.quoted_txn_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM {S}.TRANSACTIONS x WHERE x.txn_id = t.quoted_txn_id);

-- Requested amount above both the balance and the quoted transfer, unexplained.
INSERT INTO {S}.REQ_FINDINGS
SELECT t.request_id, t.account_id, 'REQUESTED_EXCEEDS', 'Requested amount', 'CONFLICT',
       CONCAT('Requested ', CAST(t.requested_amount AS VARCHAR(30)), ' exceeds both the balance at the reference time (',
              CAST(s.balance_ref AS VARCHAR(30)), ') and the quoted transfer (',
              CAST(CAST(COALESCE(x.amount, 0) AS DECIMAL(18,2)) AS VARCHAR(30)), ')')
FROM {S}.REQUEST_TARGETS t
JOIN {S}.REQUESTS r ON r.request_id = t.request_id
JOIN {S}.SIZING s ON s.case_id = r.case_id AND s.account_id = t.account_id
LEFT JOIN {S}.TRANSACTIONS x ON x.txn_id = t.quoted_txn_id
WHERE t.requested_scope = 'AMOUNT'
  -- A quoted transfer the account is not party to says nothing about the
  -- amount (that mismatch is reported separately).
  AND (x.txn_id IS NULL OR COALESCE(x.to_acct, '-') = t.account_id OR COALESCE(x.from_acct, '-') = t.account_id)
  AND CAST(t.requested_amount AS DOUBLE PRECISION) >
      GREATEST(CAST(s.balance_ref AS DOUBLE PRECISION), CAST(COALESCE(x.amount, 0) AS DOUBLE PRECISION)) + 0.01;

DROP TABLE IF EXISTS {S}.REQ_STATUS;
CREATE TABLE {S}.REQ_STATUS AS
SELECT r.request_id, r.case_id,
       CASE WHEN COALESCE(f.n_conflict, 0) > 0 THEN 'CONFLICTING'
            WHEN COALESCE(f.n_missing, 0) > 0 THEN 'INCOMPLETE'
            ELSE 'COMPLETE' END AS status,
       COALESCE(f.n_missing, 0) AS n_missing, COALESCE(f.n_conflict, 0) AS n_conflict
FROM {S}.REQUESTS r
LEFT JOIN (SELECT request_id,
                  SUM(CASE WHEN kind = 'MISSING' THEN 1 ELSE 0 END) AS n_missing,
                  SUM(CASE WHEN kind = 'CONFLICT' THEN 1 ELSE 0 END) AS n_conflict
           FROM {S}.REQ_FINDINGS GROUP BY request_id) f ON f.request_id = r.request_id;
