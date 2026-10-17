"""Ground-truth provenance ledger.

An independent, row-by-row implementation of the three allocation conventions
(pro-rata, FIFO, LIFO). It is deliberately written in a different style from
the set-based SQL engine (explicit lot queues and stacks instead of interval
arithmetic), so that agreement between the two is meaningful evidence.

Shared rules (stated in docs/method.md):
  * transactions are applied in (timestamp, sequence) order; only COMPLETED
    postings count; a completed reversal reduces the original transfer;
  * a debit larger than the balance overdraws; a later credit first repays the
    overdraft and that part is "absorbed";
  * FIFO: oldest funds leave first; LIFO: newest funds leave first; a transfer's
    payload keeps its internal order when it lands in the receiving account;
  * pro-rata: every debit carries the account's current disputed proportion.
"""
from __future__ import annotations

import heapq
from collections import defaultdict

EPS = 1e-9
DUST = 1.0   # a case's disputed funds on one transfer below this are not traced further


class FifoBook:
    """Lots oldest-first: list of [amount, case_or_None]; debt = overdraft."""
    __slots__ = ("lots", "debt")

    def __init__(self, clean: float):
        self.lots = [[clean, None]] if clean > EPS else []
        self.debt = max(-clean, 0.0)

    def credit(self, pieces):
        # pieces: list of [amount, case_or_None] in payload order
        out_absorbed = []
        for amt, case in pieces:
            if self.debt > EPS:
                take = min(self.debt, amt)
                self.debt -= take
                amt -= take
                if case is not None and take > EPS:
                    out_absorbed.append((case, take))
            if amt > EPS:
                if self.lots and self.lots[-1][1] == case:
                    self.lots[-1][0] += amt
                else:
                    self.lots.append([amt, case])
        return out_absorbed

    def debit(self, x):
        pieces = []
        while x > EPS and self.lots:
            lot = self.lots[0]
            take = min(lot[0], x)
            pieces.append([take, lot[1]])
            lot[0] -= take
            x -= take
            if lot[0] <= EPS:
                self.lots.pop(0)
        if x > EPS:
            self.debt += x
            pieces.append([x, None])
        return pieces

    def purge(self, case):
        merged = []
        for amt, c in self.lots:
            c = None if c == case else c
            if merged and merged[-1][1] == c:
                merged[-1][0] += amt
            else:
                merged.append([amt, c])
        self.lots = merged

    def held(self):
        d = defaultdict(float)
        for amt, case in self.lots:
            if case is not None:
                d[case] += amt
        return d


class LifoBook(FifoBook):
    """Stack bottom-first; debits pop from the top."""

    def debit(self, x):
        popped = []
        while x > EPS and self.lots:
            lot = self.lots[-1]
            take = min(lot[0], x)
            popped.append([take, lot[1]])
            lot[0] -= take
            x -= take
            if lot[0] <= EPS:
                self.lots.pop()
        if x > EPS:
            self.debt += x
            popped.append([x, None])
        # Payload order bottom->top so the receiver keeps the source's order.
        popped.reverse()
        return popped


def build_ledger(accounts, txns, cases, ref_epoch, disputed, observable, tainted_accounts,
                 balance_probes):
    """Replay all completed transactions in order.

    accounts: {account_id: opening_balance}
    txns: list of dicts (true, deduplicated, reversal-netted, completed) with
          keys txn_id, seq, epoch, frm, to, amount, channel
    cases: list of case ids
    ref_epoch: {case_id: reference epoch}
    disputed: {txn_id: case_id} for the reported victim transfers
    observable: set of observable account ids
    tainted_accounts: set of accounts with planted record defects
    balance_probes: {case_id: [account_ids]} -> balance at the case reference time

    Returns (ledger rows, probe balances, tainted (case, account) set, edge carried rows, dust rows)
    """
    bal = {a: (b if b is not None else 0.0) for a, b in accounts.items()}
    pr = {}      # account -> {case: disputed}
    fifo = {}    # account -> FifoBook
    lifo = {}    # account -> LifoBook
    holders = defaultdict(set)   # case -> accounts that ever held its funds
    victims = {}
    tainted = set()
    ledger, probes = [], {}
    carried = []
    dust = []

    refs = [(ref_epoch[c], c) for c in cases]
    heapq.heapify(refs)

    def purge(case):
        for a in holders[case]:
            if a in pr:
                pr[a].pop(case, None)
            if a in fifo:
                fifo[a].purge(case)
                lifo[a].purge(case)
        holders[case] = set()

    def snapshot(case):
        for a in holders[case]:
            p = pr.get(a, {}).get(case, 0.0)
            f = fifo[a].held().get(case, 0.0) if a in fifo else 0.0
            l = lifo[a].held().get(case, 0.0) if a in lifo else 0.0
            for conv, v in (("PR", p), ("FIFO", f), ("LIFO", l)):
                ledger.append((case, a, conv, v))
        for a in balance_probes.get(case, []):
            probes[(case, a)] = bal.get(a)

    def undust(pieces, conv):
        tot = defaultdict(float)
        for v, c in pieces:
            if c is not None:
                tot[c] += v
        small = {c for c, v in tot.items() if v < DUST}
        for c in small:
            dust.append((c, t["txn_id"], conv, tot[c]))
        return [[v, None if c in small else c] for v, c in pieces]

    def ensure_books(a):
        if a not in fifo:
            fifo[a] = FifoBook(bal[a])
            lifo[a] = LifoBook(bal[a])
            pr.setdefault(a, {})

    for t in txns:
        while refs and refs[0][0] < t["epoch"]:
            c_done = heapq.heappop(refs)[1]
            snapshot(c_done)
            purge(c_done)

        frm, to, x = t["frm"], t["to"], t["amount"]
        case0 = disputed.get(t["txn_id"])

        # ---------------- debit side
        pr_out, fifo_out, lifo_out = {}, [[x, None]], [[x, None]]
        if case0 is not None:
            victims[case0] = frm
            # Funds leaving the victim become disputed for this case.
            pr_out = {case0: x}
            fifo_out = [[x, case0]]
            lifo_out = [[x, case0]]
            if frm in bal:
                bal[frm] -= x
        elif frm is not None and frm in bal:
            b = bal[frm]
            if frm in fifo:
                share = 1.0 if b <= EPS else min(1.0, x / b)
                d = pr[frm]
                for c in list(d):
                    out = d[c] * share
                    if out >= DUST:
                        pr_out[c] = out
                    elif out > EPS:
                        dust.append((c, t["txn_id"], "PR", out))
                    d[c] -= out
                    if d[c] <= EPS:
                        del d[c]
                fifo_out = undust(fifo[frm].debit(x), "FIFO")
                lifo_out = undust(lifo[frm].debit(x), "LIFO")
            bal[frm] = b - x

        payload_cases = set(pr_out) | {c for _, c in fifo_out if c is not None} \
            | {c for _, c in lifo_out if c is not None}
        any_disputed = bool(payload_cases)
        material = set()
        if any_disputed:
            row = defaultdict(lambda: [0.0, 0.0, 0.0])
            for c, v in pr_out.items():
                row[c][0] += v
            for v, c in fifo_out:
                if c is not None:
                    row[c][1] += v
            for v, c in lifo_out:
                if c is not None:
                    row[c][2] += v
            for c, (p, f, l) in row.items():
                carried.append((c, t["txn_id"], p, f, l))
                if max(p, f, l) >= 1.0:
                    material.add(c)

        # ---------------- credit side
        if to is None or to not in observable:
            continue
        if any_disputed and any(victims.get(c) == to for c in payload_cases):
            # Funds returned to the victim leave the trail (treated as terminal).
            bal[to] = bal.get(to, 0.0) + x
            continue
        if any_disputed:
            ensure_books(to)
            for c in payload_cases:
                holders[c].add(to)
            for c in material:
                if to in tainted_accounts or (frm is not None and (c, frm) in tainted):
                    tainted.add((c, to))
        b = bal.get(to, 0.0)
        if to in fifo:
            absorbed_frac = 0.0 if b >= 0 else min(x, -b) / x
            for c, v in pr_out.items():
                pr[to][c] = pr[to].get(c, 0.0) + v * (1 - absorbed_frac)
            fifo[to].credit(fifo_out)
            lifo[to].credit(lifo_out)
        bal[to] = b + x

    while refs:
        snapshot(heapq.heappop(refs)[1])

    return ledger, probes, tainted, carried, dust
