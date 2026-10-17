# Method

TraceHold sizes how much of a reported fraud's money the transaction records support as still sitting
in each account at a stated reference time. Every step runs as set-based SQL inside Exasol Personal
(`database/`); the Python layer only orders the scripts and repeats the layer pass until nothing changes.

## Pipeline

| Stage | Script | What it does |
|---|---|---|
| Prepare | `10_prepare.sql` | Keeps completed postings; nets completed reversals into the original transfer; drops duplicate postings (same parties, amount and reference within 10 minutes); builds one ledger row per account posting with running balance, FIFO axes and pro-rata log factors (window functions); flags accounts with a missing opening balance or a gap (reconstructed closing ≠ statement). |
| Clock skew | `10_prepare.sql` | A debit that overdraws, and is cured by a credit within 120 s, is ordered just after that credit. |
| Cases | `11_case_ref.sql` | Reference time per case: when the request was received (configurable: analysis time or a fixed time). |
| Trace | `20_trace_seed.sql`, `21_trace_step.sql`, `22_trace_swap.sql` | Seeds the reported disputed transfers, then repeats one layer pass for all cases and all conventions until the state is stable. No recursion and no UDFs are needed (Exasol Personal has no `WITH RECURSIVE`). |
| Trail | `30_trail.sql`, `31_taint_step.sql` | Trail edges with the amount carried under each convention and a terminal state; propagates "cannot be sized" downstream of defective records. |
| Sizing | `32_sizing.sql` | Retained amount per case and account under each convention, range, traceable share, status, conservation check. |
| Requests | `40_requests.sql` | CF1 completeness (checklist table, configurable per jurisdiction) and consistency checks. |
| Review | `50_review.sql` | CF5 classification against the supported range, facts for exceptional cases, CF4 dilution by layer. |
| Additional | `60_additional.sql` | AF1 lien review queue, AF4 speed of movement. |
| Evidence | `70_evidence.sql`, `80_summary.sql` | Source records behind every figure; case summaries. |

## Allocation conventions

Money has no physical identity once mixed, so "which part of the balance is disputed" depends on a
convention. All three are computed side by side, per case.

**Pro-rata.** Each debit carries the account's current disputed proportion. With `L` the running sum of
`ln(1 − share)` over the account's debits, the disputed amount from credit *j* still present just
before debit *k* is `d_j · exp(L(k−1) − L(j))`, and debit *k* carries `share_k` of the total. This turns
a sequential recurrence into window functions and a join.

**FIFO.** Each account has a cumulative-inflow axis (the opening balance occupies `[0, opening)`, then
each credit its own interval). Debit *k* consumes `[cout_before, cout_before + amount)` of that axis.
Disputed funds are intervals on the axis; a debit carries their intersection with its consumed
interval, mapped onto the receiving account's axis in the same order.

**LIFO (bounding case).** Disputed funds are intervals of balance "levels". A level survives while the
running minimum balance since its arrival stays above it; a debit consumes the levels between its
balance-after and that running minimum.

The supported range is the span of pro-rata and FIFO; LIFO widens it for the sensitivity view (AF2).

## Rules shared with the ground truth

* Only completed postings count; a completed reversal reduces the original transfer.
* A debit beyond the balance overdraws; a later credit first repays the overdraft and that part is
  *absorbed*.
* Transfers carrying less than ₹1 of a case's disputed funds under a convention are not traced further
  under that convention (*dust*), which keeps pro-rata from spreading fractions of a paisa through the
  whole network.
* Tracing for a case stops at its reference time.
* Funds returned to the victim, withdrawn as cash or to a wallet, taken as charges, or sent to an account
  outside the available records leave the trail (terminal states).

## Conservation check

For every case and convention: retained + exited + dust + absorbed = reported loss. Any failure is a
calculation defect.

## Statuses (CF6)

| Status | When |
|---|---|
| Determined | Pro-rata and FIFO agree to the paisa and the records are complete |
| Range | The conventions disagree; both ends are reported |
| Undeterminable | Missing opening balance, a gap in the records, or funds received from such an account |
| Out of observable scope | Funds moved to an account outside the records; a forwarded request is drafted |

## Validation

The generator (`backend/generator/ledger.py`) contains an independent, row-by-row implementation of the
same three conventions using explicit lot queues and stacks. The SQL engine is compared with it in
`backend/app/evaluation.py`. On the large synthetic tier, every conservation check passes and more than 99.8%
of account-level amounts agree to the paisa. The remaining differences come from 4 of 2,400 cases with
planted clock-skew defects, where the skew heuristic orders postings differently from the truth.

## AI at the edges (CF9, AF7, AF8)

No model produces or changes a figure. The calculation path (`engine.py`, `playground.py`, the SQL in
`database/`) never imports the AI package; `tests/test_ai_boundary.py` checks this and runs the worked example
with AI switched off and on to show the figures are identical.

| Feature | What the model does | What decides whether its output is used |
|---|---|---|
| CF9 reading letters (`app/ai/extract.py`) | Returns each checklist field with the exact text it came from | The quote must appear in the letter; the value must follow from the quote (amounts re-read in digits, English, Hinglish or Devanagari); formats; cross-check with the transaction records; digits and words next to them must agree. Failures are not used; two values for one field are a conflict and never resolved. A person confirms every field (stored with name and time). |
| AF7 questions (`app/ai/ask.py`) | Picks a prepared query or drafts one SELECT, then words a short answer | Only the `TH_RESULTS` views may be queried; the query runs through Exasol's MCP server as the read-only user `TH_ASK` (Exasol itself refuses anything else); every number in the wording must appear in the rows, otherwise only the rows are shown. |
| AF8 rewording (`app/ai/reword.py`) | Rewords the template letter for the account holder | Every amount, date, time, account and reference must be unchanged, nothing dropped, no claim about the holder added; otherwise the template is kept. |

Every call is logged in Exasol (`AI_LOG`: model, prompt version, input, output, time) with temperature 0 and a
fixed seed. Only synthetic data is sent. The synthetic letters (`backend/generator/letters.py`) are split into
24 development letters (used to tune prompts) and 60 held-out letters (used for the reported results); their
answer key is in `TRACEHOLD_GT.LETTER_TRUTH`, which the extraction never reads.

## Known limitations

* The conventions are estimation tools, not legal findings about who owns money.
* Clock-skew correction is a heuristic (overdraft cured within the tolerance).
* A records gap is detected only through the closing statement balance, for the whole data window.
* The AF1 review rules follow a commentary on the 2 January 2026 procedure and must be checked against
  the primary text; they are configurable (`backend/app/engine.py`, `Config`).
* All data is synthetic. Results do not describe real recoveries or harms.
* AI results are measured on synthetic letters and fixed question sets; they are not claims about real-world
  accuracy. The free Groq tier limits throughput (about four letter readings a minute).
