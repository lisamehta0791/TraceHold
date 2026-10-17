"""TraceHold synthetic data generator.

Produces a fully synthetic banking dataset (accounts, transactions, fraud cases,
hold requests, restraints) with injected defects and a separate ground truth.
Nothing here is real data; all names, banks and references are invented.

    python backend/generator/generate.py --scale 1.0 --seed 2026 --out data/L

Outputs CSV files for the analysis schema plus a gt/ folder for the
ground-truth schema, and manifest.json with row counts and checksums.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger import build_ledger  # noqa: E402

GENERATOR_VERSION = "1.0.0"
EPOCH0 = datetime(2026, 1, 1)
WINDOW_START = datetime(2026, 5, 1)
WINDOW_END = datetime(2026, 10, 12, 23, 59, 59)
AS_OF = datetime(2026, 10, 15)

INSTITUTIONS = [
    # id, name, kind, observable
    ("BK01", "Narmada Commercial Bank", "BANK", True),
    ("BK02", "Kaveri Co-operative Bank", "BANK", True),
    ("BK03", "Deccan Plateau Bank", "BANK", True),
    ("BK04", "Saraswati Urban Bank", "BANK", True),
    ("BK05", "Malabar Coast Bank", "BANK", True),
    ("BK06", "Aravalli Gramin Bank", "BANK", True),
    ("BK07", "Godavari Federal Bank", "BANK", True),
    ("BK08", "Konkan Merchants Bank", "BANK", True),
    ("BK09", "Brahmaputra Valley Bank", "BANK", False),
    ("BK10", "Thar Desert Bank", "BANK", False),
    ("BK11", "Sunderbans Small Finance Bank", "BANK", False),
    ("WL01", "PaisaPocket Wallet", "WALLET", False),
]
OBS_BANKS = [i[0] for i in INSTITUTIONS if i[3] and i[2] == "BANK"]
NONOBS_BANKS = [i[0] for i in INSTITUTIONS if not i[3] and i[2] == "BANK"]

FIRST = ["Aarav", "Vivaan", "Aditya", "Ishaan", "Kabir", "Rohan", "Arjun", "Sai", "Reyansh",
         "Ananya", "Diya", "Isha", "Kavya", "Meera", "Saanvi", "Priya", "Nisha", "Pooja",
         "Rahul", "Vikram", "Suresh", "Lakshmi", "Farhan", "Zoya", "Gurpreet", "Harleen",
         "Tenzin", "Joseph", "Mary", "Arif", "Deepa", "Manoj", "Sunita", "Ravi", "Anil"]
LAST = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Patel", "Shah", "Singh", "Khan",
        "Das", "Ghosh", "Banerjee", "Mehta", "Joshi", "Kulkarni", "Menon", "Pillai",
        "Rao", "Gupta", "Agarwal", "Chauhan", "Yadav", "Mishra", "Fernandes", "D'Souza"]
BIZ = ["Traders", "Enterprises", "Stores", "Agencies", "Textiles", "Electronics", "Foods",
       "Logistics", "Pharma", "Hardware", "Motors", "Jewellers", "Kirana", "Infotech"]
DISTRICTS = ["Jaipur", "Jodhpur", "Udaipur", "Kota", "Ajmer", "Bikaner", "Alwar", "Bhilwara",
             "Pune", "Nagpur", "Indore", "Bhopal", "Lucknow", "Patna", "Ranchi", "Mysuru",
             "Madurai", "Kochi", "Guwahati", "Surat"]
DESIGNATIONS = ["Inspector of Police", "Sub-Inspector of Police", "Assistant Commissioner of Police",
                "Deputy Superintendent of Police", "Station House Officer"]
PROVISIONS = ["Section 106 BNSS 2023; Section 318(4) BNS; Section 66D IT Act 2000",
              "Section 106 BNSS 2023; Section 66C, 66D IT Act 2000",
              "Section 106 BNSS 2023; Section 318 BNS"]

SCENARIO_MIX = [
    ("SIMPLE_CHAIN", 0.16), ("SPLIT_MERGE", 0.12), ("COMMINGLED", 0.13),
    ("INNOCENT_RECIPIENT", 0.12), ("BUSINESS_TURNOVER", 0.10), ("RAPID_CASHOUT", 0.10),
    ("CROSS_INSTITUTION", 0.11), ("REVERSAL_FAILED", 0.08), ("SHARED_ACCOUNT", 0.08),
]


def ep(dt: datetime) -> int:
    return int((dt - EPOCH0).total_seconds())


def dt_of(e: int) -> datetime:
    return EPOCH0 + timedelta(seconds=int(e))


def fmt_ts(e: int) -> str:
    return dt_of(e).strftime("%Y-%m-%d %H:%M:%S")


class Gen:
    def __init__(self, scale: float, seed: int):
        self.rng = random.Random(seed)
        self.scale = scale
        self.seed = seed
        self.n_individual = int(110_000 * scale)
        self.n_business = int(4_500 * scale)
        self.n_nonobs = int(12_000 * scale)
        self.n_cases = max(40, int(2_400 * scale))
        self.accounts = {}          # id -> dict
        self.next_acc = 1
        self.events = []            # heap items for simulation
        self.txns = []              # final completed + other postings (true data)
        self.seq = 0
        self.ref_counter = 0
        self.cases = []
        self.chain = []             # (case_id, txn_id, layer)
        self.scenario = {}
        self.disputed = {}          # txn_id -> case_id
        self.case_accounts = defaultdict(list)   # case -> [(account, layer, recv_txn)]
        self.mule_only = set()      # accounts with no background activity

    # ------------------------------------------------------------ accounts
    def new_account(self, inst, acct_type, opening, opened=None, label=None, quiet=False):
        aid = f"AC{self.next_acc:07d}"
        self.next_acc += 1
        r = self.rng
        if label is None:
            if acct_type == "BUSINESS":
                label = f"{r.choice(LAST)} {r.choice(BIZ)}"
            else:
                label = f"{r.choice(FIRST)} {r.choice(LAST)}"
        if opened is None:
            opened = WINDOW_START - timedelta(days=r.randint(200, 4000))
        self.accounts[aid] = dict(
            account_id=aid, institution_id=inst, holder_label=label, acct_type=acct_type,
            opened_date=opened.strftime("%Y-%m-%d"), opening=round(opening, 2))
        if quiet:
            self.mule_only.add(aid)
        return aid

    def build_population(self):
        r = self.rng
        self.individuals, self.businesses, self.nonobs = [], [], []
        for _ in range(self.n_individual):
            bal = min(r.lognormvariate(math.log(45_000), 1.0), 4_000_000)
            self.individuals.append(self.new_account(r.choice(OBS_BANKS), "INDIVIDUAL", bal))
        for _ in range(self.n_business):
            bal = min(r.lognormvariate(math.log(1_800_000), 1.0), 80_000_000)
            self.businesses.append(self.new_account(r.choice(OBS_BANKS), "BUSINESS", bal))
        for _ in range(self.n_nonobs):
            self.nonobs.append(self.new_account(r.choice(NONOBS_BANKS), "INDIVIDUAL", 0.0))
        self.wallet_accts = [self.new_account("WL01", "BUSINESS", 0.0, label=f"Wallet pool {i}")
                             for i in range(1, 6)]
        self.employer = {a: r.choice(self.businesses) for a in self.individuals if r.random() < 0.7}

    # ------------------------------------------------------------ events
    def push(self, epoch, kind, frm, to, amount_rule, channel, case=None, layer=None, tag=None,
             status="COMPLETED", reversal_of=None):
        self.seq_push = getattr(self, "seq_push", 0) + 1
        heapq.heappush(self.events, (epoch, self.seq_push, kind, frm, to, amount_rule, channel,
                                     case, layer, tag, status, reversal_of))

    def background_events(self):
        r = self.rng
        t0, t1 = ep(WINDOW_START), ep(WINDOW_END)
        days = (t1 - t0) / 86400
        # Individuals
        for a in self.individuals:
            n = self._poisson(0.075 * days)
            for _ in range(n):
                e = r.randint(t0, t1)
                u = r.random()
                if u < 0.45:
                    self.push(e, "BG", a, r.choice(self.individuals), ("want", r.lognormvariate(math.log(1500), 1.0)), r.choice(["UPI", "UPI", "IMPS"]))
                elif u < 0.90:
                    self.push(e, "BG", a, r.choice(self.businesses), ("want", r.lognormvariate(math.log(900), 1.1)), r.choice(["UPI", "CARD"]))
                elif u < 0.96:
                    self.push(e, "BG", a, None, ("want", r.choice([500, 1000, 2000, 3000, 5000, 10000])), "CASH_WD")
                else:
                    self.push(e, "BG", a, r.choice(self.nonobs), ("want", r.lognormvariate(math.log(2500), 1.0)), "IMPS")
        # Businesses: heavy turnover
        for b in self.businesses:
            n = self._poisson(0.9 * days)
            for _ in range(n):
                e = r.randint(t0, t1)
                u = r.random()
                if u < 0.35:
                    self.push(e, "BG", b, r.choice(self.individuals), ("want", r.lognormvariate(math.log(4000), 1.0)), "IMPS")
                elif u < 0.85:
                    self.push(e, "BG", b, r.choice(self.businesses), ("want", r.lognormvariate(math.log(25000), 1.1)), r.choice(["NEFT", "RTGS", "IMPS"]))
                elif u < 0.95:
                    self.push(e, "BG", b, None, ("want", r.choice([5000, 10000, 20000, 50000])), "CASH_WD")
                else:
                    self.push(e, "BG", b, r.choice(self.nonobs), ("want", r.lognormvariate(math.log(30000), 1.0)), "NEFT")
        # Salaries on the first working day of each month
        d = WINDOW_START
        while d < WINDOW_END:
            if d.day == 1:
                for a, emp in self.employer.items():
                    e = ep(d) + 9 * 3600 + r.randint(0, 6 * 3600)
                    self.push(e, "BG", emp, a, ("want", round(r.lognormvariate(math.log(35000), 0.5), -2)), "NEFT", tag="SALARY")
            d += timedelta(days=1)
        # Inflows from other banks keep the economy topped up
        for a in r.sample(self.individuals, len(self.individuals) // 4):
            for _ in range(self._poisson(3)):
                self.push(r.randint(t0, t1), "BG", r.choice(self.nonobs), a, ("fixed", round(r.lognormvariate(math.log(8000), 0.9), 2)), "IMPS")
        # Monthly SMS / maintenance charges on a subset
        for a in r.sample(self.individuals, len(self.individuals) // 10):
            for m in range(5, 11):
                self.push(ep(datetime(2026, m, 28, 2, 0)) + r.randint(0, 3600), "BG", a, None, ("want", 17.70), "CHARGE")
        # Quarterly interest
        for a in r.sample(self.individuals, len(self.individuals) // 5):
            self.push(ep(datetime(2026, 7, 1, 1, 0)) + r.randint(0, 3600), "BG", None, a, ("fixed", round(r.uniform(50, 900), 2)), "INTEREST")

    def _poisson(self, lam):
        if lam > 30:
            return max(0, int(self.rng.gauss(lam, math.sqrt(lam))))
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= L:
                return k
            k += 1

    # ------------------------------------------------------------ scenarios
    def mule(self, bank=None):
        r = self.rng
        return self.new_account(bank or r.choice(OBS_BANKS), "INDIVIDUAL", round(r.uniform(0, 4000), 2),
                                opened=WINDOW_START - timedelta(days=r.randint(5, 120)), quiet=True)

    def established_individual(self, min_bal):
        r = self.rng
        bal = max(min_bal, r.lognormvariate(math.log(min_bal * 2.5), 0.6))
        return self.new_account(r.choice(OBS_BANKS), "INDIVIDUAL", bal,
                                opened=WINDOW_START - timedelta(days=r.randint(900, 5000)))

    def build_cases(self):
        r = self.rng
        names = [s for s, _ in SCENARIO_MIX]
        weights = [w for _, w in SCENARIO_MIX]
        t0, t1 = ep(WINDOW_START + timedelta(days=10)), ep(WINDOW_END - timedelta(days=3))
        self.shared_hubs = []
        # Case 1 is the worked example from Section 4.7 of the project document.
        self.worked_example()
        for cid in range(2, self.n_cases + 1):
            sc = r.choices(names, weights)[0]
            if sc == "SHARED_ACCOUNT" and not self.shared_hubs:
                sc = "SIMPLE_CHAIN"
            fraud = r.randint(t0, t1)
            loss = round(min(max(r.lognormvariate(math.log(65_000), 1.0), 4_000), 2_500_000), 2)
            if r.random() < 0.3:
                loss = round(loss, -3)
            victim = self.established_individual(loss * 1.3)
            self.add_case(cid, sc, victim, loss, fraud)

    def add_case(self, cid, sc, victim, loss, fraud):
        r = self.rng
        self.scenario[cid] = sc
        self.cases.append(dict(case_id=cid, victim=victim, loss=loss, fraud=fraud))
        # Victim pays in 1-3 instalments to the first-layer account(s).
        n_inst = 1 if r.random() < 0.7 else r.randint(2, 3)
        parts = self._split(loss, n_inst)
        l1 = self.mule()
        if sc == "SHARED_ACCOUNT" and r.random() < 0.5:
            l1 = r.choice(self.shared_hubs)
        t = fraud
        for p in parts:
            self.push(t, "SCRIPT", victim, l1, ("fixed", p), r.choice(["UPI", "IMPS"]), case=cid, layer=1, tag="DISPUTED")
            t += r.randint(60, 900)
        self.case_accounts[cid].append((l1, 1))
        start = t + r.randint(60, 600)
        getattr(self, "sc_" + sc.lower())(cid, l1, start, loss)

    def _split(self, total, n):
        if n == 1:
            return [total]
        cuts = sorted(self.rng.uniform(0.2, 0.8) for _ in range(n - 1))
        parts, prev = [], 0.0
        for c in cuts + [1.0]:
            parts.append(round(total * (c - prev), 2))
            prev = c
        parts[-1] = round(total - sum(parts[:-1]), 2)
        return parts

    def hop(self, cid, frm, to, t, rule, layer, channel=None, tag=None, status="COMPLETED"):
        self.push(t, "SCRIPT", frm, to, rule, channel or self.rng.choice(["IMPS", "UPI", "IMPS", "NEFT"]),
                  case=cid, layer=layer, tag=tag, status=status)
        if to is not None and to in self.accounts and self.accounts[to]["institution_id"] in OBS_BANKS:
            self.case_accounts[cid].append((to, layer))

    def chain_tail(self, cid, acct, t, layer, end):
        r = self.rng
        if end == "keep":
            return
        if end == "cash":
            for _ in range(r.randint(1, 3)):
                t += r.randint(120, 900)
                self.hop(cid, acct, None, t, ("frac", r.uniform(0.3, 0.6)), layer + 1, channel="CASH_WD")
        elif end == "wallet":
            self.hop(cid, acct, r.choice(self.wallet_accts), t + r.randint(60, 600), ("frac", r.uniform(0.85, 0.99)), layer + 1, channel="WALLET")
        elif end == "nonobs":
            self.hop(cid, acct, r.choice(self.nonobs), t + r.randint(60, 600), ("frac", r.uniform(0.6, 0.99)), layer + 1)

    def sc_simple_chain(self, cid, l1, t, loss):
        r = self.rng
        cur, depth = l1, r.randint(2, 5)
        for layer in range(2, depth + 1):
            nxt = self.mule()
            self.hop(cid, cur, nxt, t, ("frac", r.uniform(0.9, 0.99)), layer)
            cur, t = nxt, t + r.randint(120, 1200)
        if r.random() < 0.3:
            self.shared_hubs.append(cur)
        self.chain_tail(cid, cur, t, depth, r.choice(["keep", "keep", "cash", "wallet"]))

    def sc_split_merge(self, cid, l1, t, loss):
        r = self.rng
        n = r.randint(2, 4)
        fracs = self._split(1.0, n)
        mids = []
        for i, f in enumerate(fracs):
            m = self.mule()
            # Each split takes its share of what is left in l1.
            rule = ("frac", min(0.98, f / max(1e-9, sum(fracs[i:])) * 0.98))
            self.hop(cid, l1, m, t, rule, 2)
            mids.append(m)
            t += r.randint(30, 300)
        merge = self.mule()
        t += r.randint(300, 1800)
        for m in mids[:2]:
            self.hop(cid, m, merge, t, ("frac", r.uniform(0.9, 0.99)), 3)
            t += r.randint(30, 300)
        for m in mids[2:]:
            self.chain_tail(cid, m, t, 2, r.choice(["keep", "cash"]))
        if r.random() < 0.5:
            # Round trip back to the first-layer account (loop).
            t += r.randint(600, 3600)
            self.hop(cid, merge, l1, t, ("frac", r.uniform(0.3, 0.6)), 4)
            self.chain_tail(cid, l1, t + 300, 4, r.choice(["keep", "cash", "nonobs"]))
        else:
            self.chain_tail(cid, merge, t, 3, r.choice(["keep", "wallet", "nonobs"]))

    def sc_commingled(self, cid, l1, t, loss):
        r = self.rng
        big = self.established_individual(max(200_000, loss * 3))
        self.hop(cid, l1, big, t, ("frac", r.uniform(0.85, 0.98)), 2)
        # The commingled account later makes a large payment of its own.
        t2 = t + r.randint(1800, 6 * 3600)
        nxt = self.established_individual(50_000)
        self.hop(cid, big, nxt, t2, ("frac", r.uniform(0.4, 0.8)), 3)

    def sc_innocent_recipient(self, cid, l1, t, loss):
        r = self.rng
        innocent = self.established_individual(80_000)
        pay = round(min(loss * r.uniform(0.05, 0.3), 45_000), 2)
        self.hop(cid, l1, innocent, t, ("fixed", pay), 2, channel="UPI", tag="ONE_OFF")
        l2 = self.mule()
        self.hop(cid, l1, l2, t + r.randint(60, 600), ("frac", 0.97), 2)
        self.chain_tail(cid, l2, t + 900, 2, r.choice(["cash", "wallet", "keep"]))

    def sc_business_turnover(self, cid, l1, t, loss):
        r = self.rng
        biz = r.choice(self.businesses)
        self.hop(cid, l1, biz, t, ("frac", r.uniform(0.3, 0.9)), 2, channel="UPI")
        l2 = self.mule()
        self.hop(cid, l1, l2, t + r.randint(60, 600), ("frac", 0.95), 2)
        self.chain_tail(cid, l2, t + 1200, 2, r.choice(["cash", "keep", "nonobs"]))

    def sc_rapid_cashout(self, cid, l1, t, loss):
        r = self.rng
        l2 = self.mule()
        self.hop(cid, l1, l2, t, ("frac", 0.99), 2)
        t += r.randint(60, 240)
        for _ in range(r.randint(2, 5)):
            self.hop(cid, l2, None, t, ("frac", r.uniform(0.3, 0.7)), 3, channel="CASH_WD")
            t += r.randint(60, 300)

    def sc_cross_institution(self, cid, l1, t, loss):
        r = self.rng
        l2 = self.mule()
        self.hop(cid, l1, l2, t, ("frac", r.uniform(0.9, 0.99)), 2)
        t += r.randint(120, 900)
        self.hop(cid, l2, r.choice(self.nonobs), t, ("frac", r.uniform(0.5, 0.8)), 3)
        if r.random() < 0.5:
            self.hop(cid, l2, r.choice(self.nonobs), t + r.randint(60, 600), ("frac", 0.95), 3)

    def sc_reversal_failed(self, cid, l1, t, loss):
        r = self.rng
        l2 = self.mule()
        # A failed attempt, then the successful retry.
        self.hop(cid, l1, l2, t, ("frac", 0.95), 2, status="FAILED")
        self.hop(cid, l1, l2, t + 90, ("frac", 0.95), 2, tag="REVERSIBLE")
        l3 = self.mule()
        self.hop(cid, l2, l3, t + r.randint(1200, 2400), ("frac", 0.9), 3)
        self.hop(cid, l2, self.mule(), t + 200, ("frac", 0.3), 3, status="PENDING")

    def sc_shared_account(self, cid, l1, t, loss):
        r = self.rng
        hub = r.choice(self.shared_hubs)
        if hub == l1:
            hub = self.mule()
        self.hop(cid, l1, hub, t, ("frac", r.uniform(0.9, 0.99)), 2)
        self.chain_tail(cid, hub, t + r.randint(300, 1800), 2, r.choice(["keep", "cash", "nonobs"]))

    def worked_example(self):
        victim = self.new_account("BK01", "INDIVIDUAL", 250_000, label="Worked-example victim", quiet=True)
        a = self.new_account("BK02", "INDIVIDUAL", 20_000, label="Account A", quiet=True)
        b = self.new_account("BK03", "BUSINESS", 500_000, label="Account B", quiet=True)
        c = self.new_account("BK04", "INDIVIDUAL", 50_000, label="Account C", quiet=True)
        day = datetime(2026, 8, 14)
        self.scenario[1] = "WORKED_EXAMPLE"
        self.cases.append(dict(case_id=1, victim=victim, loss=100_000.0, fraud=ep(day.replace(hour=14, minute=2)),
                               ref=ep(day.replace(hour=15, minute=0))))
        self.push(ep(day.replace(hour=14, minute=2)), "SCRIPT", victim, a, ("fixed", 100_000.0), "IMPS", case=1, layer=1, tag="DISPUTED")
        self.push(ep(day.replace(hour=14, minute=10)), "SCRIPT", a, b, ("fixed", 90_000.0), "IMPS", case=1, layer=2)
        self.push(ep(day.replace(hour=15, minute=0)), "SCRIPT", b, c, ("fixed", 400_000.0), "RTGS", case=1, layer=3)
        self.case_accounts[1] += [(a, 1), (b, 2), (c, 3)]
        self.worked = (a, b, c)

    # ------------------------------------------------------------ simulation
    def simulate(self):
        bal = {a: v["opening"] for a, v in self.accounts.items()}
        r = self.rng
        while self.events:
            (e, _, kind, frm, to, rule, channel, case, layer, tag, status, rev_of) = heapq.heappop(self.events)
            if kind == "BG" and (frm in self.mule_only or to in self.mule_only):
                continue
            avail = bal.get(frm, 0.0) if frm is not None else float("inf")
            mode, v = rule
            if mode == "fixed":
                amt = v if frm is None or kind == "SCRIPT" else min(v, avail)
                if kind == "SCRIPT" and frm is not None and amt > avail:
                    # Top the victim up from another bank so the reported transfer is real.
                    if case is not None and tag == "DISPUTED":
                        self._emit(e - 3600, None, frm, round(amt - avail + 1000, 2), "NEFT", bal)
                        avail = bal[frm]
                    else:
                        amt = max(0.0, avail)
            elif mode == "frac":
                amt = avail * v
            else:  # want
                amt = min(v, avail * 0.95)
            amt = round(amt, 2)
            if amt < 10 and not (channel == "CHARGE" and amt > 0):
                continue
            if channel == "CHARGE" and avail < amt:
                continue
            txn = self._emit(e, frm, to, amt, channel, bal, status=status, reversal_of=rev_of)
            if case is not None:
                if status == "COMPLETED":
                    self.chain.append((case, txn["txn_id"], layer))
                    if tag == "DISPUTED":
                        self.disputed[txn["txn_id"]] = case
                if tag == "REVERSIBLE" and status == "COMPLETED":
                    # Partial reversal posted shortly after the original, before
                    # the receiver forwards the funds.
                    self.push(e + 300, "SCRIPT", to, frm, ("fixed", round(amt * r.uniform(0.1, 0.4), 2)),
                              channel, tag="REVERSAL", reversal_of=txn["txn_id"])
        self.final_balance = bal

    def _emit(self, e, frm, to, amt, channel, bal, status="COMPLETED", reversal_of=None):
        self.seq += 1
        self.ref_counter += 1
        txn = dict(txn_id=f"T{self.seq:010d}", seq=self.seq, epoch=e, frm=frm, to=to, amount=amt,
                   channel=channel, ref=f"UTR{(self.ref_counter * 7919 + self.seed) % 10**12:012d}",
                   status=status, reversal_of=reversal_of)
        if status == "COMPLETED":
            if frm is not None:
                bal[frm] = bal.get(frm, 0.0) - amt
            if to is not None:
                bal[to] = bal.get(to, 0.0) + amt
        self.txns.append(txn)
        return txn

    # ------------------------------------------------------------ requests
    def netted_true_txns(self):
        """Completed postings with reversals netted into their originals (true order)."""
        rev = defaultdict(float)
        for t in self.txns:
            if t["status"] == "COMPLETED" and t["reversal_of"]:
                rev[t["reversal_of"]] += t["amount"]
        out = []
        for t in self.txns:
            if t["status"] != "COMPLETED" or t["reversal_of"]:
                continue
            amt = round(t["amount"] - rev.get(t["txn_id"], 0.0), 2)
            if amt <= 0:
                continue
            out.append(dict(t, amount=amt))
        out.sort(key=lambda t: (t["epoch"], t["seq"]))
        return out

    def build_requests(self):
        r = self.rng
        by_id = {t["txn_id"]: t for t in self.txns}
        chain_by_case = defaultdict(list)
        for cid, tid, layer in self.chain:
            chain_by_case[cid].append((by_id[tid], layer))
        first_disputed = {}
        for t in self.txns:
            cid = self.disputed.get(t["txn_id"])
            if cid is not None and cid not in first_disputed:
                first_disputed[cid] = t
        self.requests, self.targets = [], []
        obs = {a for a, v in self.accounts.items() if v["institution_id"] in OBS_BANKS}
        for c in self.cases:
            cid = c["case_id"]
            if "ref" not in c:
                delay = min(max(r.lognormvariate(math.log(4 * 3600), 0.9), 40 * 60), 48 * 3600)
                c["ref"] = c["fraud"] + int(delay)
            c["case_ref"] = f"NCRP-3{dt_of(c['fraud']).strftime('%Y%m%d')}{cid:05d}"
            ref = c["ref"]
            # Accounts the police can see received funds before the request.
            received = {}
            for t, layer in sorted(chain_by_case[cid], key=lambda x: (x[0]["epoch"], x[0]["seq"])):
                if t["epoch"] <= ref and t["to"] in obs and t["to"] != c["victim"] and t["to"] not in received:
                    received[t["to"]] = (t, layer)
            sc = self.scenario[cid]
            special = set()
            if sc in ("INNOCENT_RECIPIENT", "BUSINESS_TURNOVER"):
                special = {a for a, (t, l) in received.items() if l == 2 and a not in self.mule_only}
            chosen = []
            for i, (a, (t, layer)) in enumerate(received.items()):
                if i == 0 or a in special or sc == "WORKED_EXAMPLE" or r.random() < 0.85:
                    chosen.append((a, t, layer))
            chosen = chosen[:7]
            if sc == "WORKED_EXAMPLE":
                action = "TOTAL_FREEZE"
            else:
                action = r.choices(["LIEN_AMOUNT", "DEBIT_FREEZE", "TOTAL_FREEZE"], [0.45, 0.25, 0.30])[0]
            district = r.choice(DISTRICTS)
            req = dict(request_id=cid, case_id=cid, received=ref,
                       officer=f"{r.choice(FIRST)} {r.choice(LAST)}", designation=r.choice(DESIGNATIONS),
                       agency=f"Cyber Crime Police Station, {district}",
                       contact=f"cyber.{district.lower()}@police.example.in / +91-1{r.randint(10**8, 10**9 - 1)}",
                       case_reference=c["case_ref"], legal_provision=r.choice(PROVISIONS),
                       action_type=action, stated_amount=c["loss"], quoted_txn_id=first_disputed[cid]["txn_id"])
            self.requests.append(req)
            for a, t, layer in chosen:
                whole = action != "LIEN_AMOUNT" or a in special
                self.targets.append(dict(request_id=cid, account_id=a,
                                         scope="WHOLE_BALANCE" if whole else "AMOUNT",
                                         amount=None if whole else round(min(c["loss"], t["amount"]), 2),
                                         quoted_txn_id=t["txn_id"]))

    # ------------------------------------------------------------ defects
    def plant_record_defects(self):
        """Choose record-level defects before the ground truth is computed."""
        r = self.rng
        self.planted = []
        self.missing_opening, self.deleted_txns, self.dup_rows, self.skewed = set(), set(), [], {}
        self.tainted_accounts = set()
        obs = {a for a, v in self.accounts.items() if v["institution_id"] in OBS_BANKS}
        by_acct = defaultdict(list)
        for t in self.txns:
            if t["status"] == "COMPLETED" and not t["reversal_of"]:
                for a in (t["frm"], t["to"]):
                    if a is not None:
                        by_acct[a].append(t)
        chain_ids = {tid for _, tid, _ in self.chain}
        by_id = {t["txn_id"]: t for t in self.txns}
        cases = [c for c in self.cases if c["case_id"] != 1]
        for c in r.sample(cases, int(len(cases) * 0.03)):
            accs = [a for a, l in self.case_accounts[c["case_id"]] if a in obs]
            if accs:
                a = r.choice(accs)
                self.missing_opening.add(a)
                self.tainted_accounts.add(a)
                self.planted.append(("MISSING_OPENING_BALANCE", c["case_id"], None, a, None, "opening balance removed"))
        n_gap = 0
        for c in r.sample(cases, len(cases)):
            if n_gap >= int(len(cases) * 0.03):
                break
            accs = [a for a, l in self.case_accounts[c["case_id"]] if a in obs]
            cands = [t for a in accs for t in by_acct[a] if t["txn_id"] not in chain_ids
                     and t["txn_id"] not in self.disputed]
            if cands:
                n_gap += 1
                t = r.choice(cands)
                self.deleted_txns.add(t["txn_id"])
                for a in (t["frm"], t["to"]):
                    if a in obs:
                        self.tainted_accounts.add(a)
                self.planted.append(("MISSING_TXN_RECORD", c["case_id"], None,
                                     t["frm"] if t["frm"] in accs else t["to"], t["txn_id"],
                                     "transaction record removed"))
        hop_cands = [(cid, by_id[tid]) for cid, tid, layer in self.chain if layer >= 2]
        for cid, t in r.sample(hop_cands, min(len(hop_cands), int(len(cases) * 0.03))):
            self.dup_rows.append(t)
            self.planted.append(("DUPLICATE_RECORD", cid, None, t["frm"], t["txn_id"], "transfer posted twice"))
        # Clock skew: an onward hop from a simple-chain mule appears to happen
        # before the credit that funded it.
        # Latest credit into each account before each of its onward hops.
        credits_into = defaultdict(list)
        for cid, tid, layer in self.chain:
            t = by_id[tid]
            credits_into[(cid, t["to"])].append(t)
        incoming = {}
        for cid, tid, layer in self.chain:
            t = by_id[tid]
            prior = [c for c in credits_into.get((cid, t["frm"]), []) if c["epoch"] <= t["epoch"]]
            if prior:
                incoming[(cid, t["frm"], tid)] = max(prior, key=lambda c: (c["epoch"], c["seq"]))
        skew_c = [(cid, by_id[tid]) for cid, tid, layer in self.chain
                  if layer >= 2 and self.scenario[cid] in ("SIMPLE_CHAIN", "RAPID_CASHOUT")
                  and by_id[tid]["frm"] in self.mule_only and (cid, by_id[tid]["frm"], tid) in incoming]
        for cid, t in r.sample(skew_c, min(len(skew_c), int(len(cases) * 0.04))):
            if t["txn_id"] in self.skewed:
                continue
            credit = incoming[(cid, t["frm"], t["txn_id"])]
            self.skewed[t["txn_id"]] = credit["epoch"] - r.randint(10, 90)
            self.planted.append(("CLOCK_SKEW", cid, None, t["frm"], t["txn_id"], "timestamp earlier than funding credit"))

    def plant_request_defects(self, probes):
        r = self.rng
        kinds = ["MISSING_OFFICER", "MISSING_DESIGNATION", "MISSING_CONTACT", "MISSING_CASE_REF",
                 "MISSING_LEGAL_PROVISION", "MISSING_AMOUNT", "MISSING_TXN", "AMOUNT_MISMATCH",
                 "AMOUNT_UNIT", "TXN_NOT_FOUND", "TARGET_MISMATCH", "REUSED_REFERENCE",
                 "REQUESTED_EXCEEDS", "DUPLICATE_REQUEST"]
        amount_of = {t["txn_id"]: t["amount"] for t in self.txns}
        bg = [t["txn_id"] for t in r.sample(self.txns, min(2000, len(self.txns)))
              if t["status"] == "COMPLETED" and t["txn_id"] not in self.deleted_txns]
        tg_by_req = defaultdict(list)
        for tg in self.targets:
            tg_by_req[tg["request_id"]].append(tg)
        dups = []
        for req in list(self.requests):
            if req["case_id"] == 1 or r.random() > 0.30:
                continue
            rid = req["request_id"]
            tgs = tg_by_req[rid]
            picked = r.sample(kinds, r.choice([1, 1, 2]))
            # Defects that touch the same field are not stacked.
            for group in ({"MISSING_AMOUNT", "AMOUNT_MISMATCH", "AMOUNT_UNIT"}, {"MISSING_TXN", "TXN_NOT_FOUND"},
                          {"MISSING_CASE_REF", "REUSED_REFERENCE"}):
                hits = [k for k in picked if k in group]
                for k in hits[1:]:
                    picked.remove(k)
            for k in picked:
                if k == "MISSING_OFFICER":
                    req["officer"] = None
                elif k == "MISSING_DESIGNATION":
                    req["designation"] = None
                elif k == "MISSING_CONTACT":
                    req["contact"] = None
                elif k == "MISSING_CASE_REF":
                    req["case_reference"] = None
                elif k == "MISSING_LEGAL_PROVISION":
                    req["legal_provision"] = None
                elif k == "MISSING_AMOUNT":
                    req["stated_amount"] = None
                elif k == "MISSING_TXN":
                    req["quoted_txn_id"] = None
                elif k == "AMOUNT_MISMATCH":
                    if req["stated_amount"] is None:
                        continue
                    req["stated_amount"] = round(req["stated_amount"] * r.choice([0.5, 1.25, 1.6, 2.0]), 2)
                elif k == "AMOUNT_UNIT":
                    if req["stated_amount"] is None:
                        continue
                    req["stated_amount"] = round(req["stated_amount"] * 100, 2)
                elif k == "TXN_NOT_FOUND":
                    req["quoted_txn_id"] = f"T9{r.randint(10**8, 10**9 - 1)}"
                elif k == "TARGET_MISMATCH":
                    if not tgs:
                        continue
                    tg = r.choice(tgs)
                    tg["quoted_txn_id"] = r.choice(bg)
                    self.planted.append((k, req["case_id"], rid, tg["account_id"], tg["quoted_txn_id"], ""))
                    continue
                elif k == "REUSED_REFERENCE":
                    other = r.choice(self.requests)
                    if other is req or not other["case_reference"]:
                        continue
                    req["case_reference"] = other["case_reference"]
                elif k == "REQUESTED_EXCEEDS":
                    if not tgs:
                        continue
                    tg = r.choice(tgs)
                    bal = probes.get((req["case_id"], tg["account_id"])) or 0.0
                    hop = amount_of.get(tg["quoted_txn_id"], 0.0)
                    tg["scope"] = "AMOUNT"
                    tg["amount"] = round(max(bal, hop) * 2.5 + 10_000, 2)
                    self.planted.append((k, req["case_id"], rid, tg["account_id"], None, ""))
                    continue
                elif k == "DUPLICATE_REQUEST":
                    dups.append(req)
                    continue
                self.planted.append((k, req["case_id"], rid, None, None, ""))
        next_id = max(q["request_id"] for q in self.requests) + 1
        for req in dups:
            d = dict(req, request_id=next_id, received=req["received"] + r.randint(600, 7200))
            self.requests.append(d)
            for tg in tg_by_req[req["request_id"]]:
                self.targets.append(dict(tg, request_id=next_id))
            self.planted.append(("DUPLICATE_REQUEST", req["case_id"], next_id, None, None,
                                 f"duplicate of {req['request_id']}"))
            next_id += 1

    def build_restraints(self, probes):
        r = self.rng
        req_by_id = {q["request_id"]: q for q in self.requests}
        dup_ids = {p[2] for p in self.planted if p[0] == "DUPLICATE_REQUEST"}
        self.restraints = []
        rid = 1
        for tg in self.targets:
            if tg["request_id"] in dup_ids:
                continue
            req = req_by_id[tg["request_id"]]
            bal = max(probes.get((req["case_id"], tg["account_id"])) or 0.0, 0.0)
            held = round(min(tg["amount"], bal) if tg["scope"] == "AMOUNT" else bal, 2)
            start = dt_of(req["received"]).date()
            age = (AS_OF.date() - start).days
            status = r.choices(["OPEN", "CLOSURE_REPORT", "CLEAN_CHIT", "CLOSED"], [0.80, 0.08, 0.07, 0.05])[0]
            upd = start + timedelta(days=r.randint(0, max(age, 0))) if r.random() < 0.65 else start
            released = (upd + timedelta(days=r.randint(0, 10))).isoformat() if status == "CLOSED" else None
            self.restraints.append(dict(
                restraint_id=rid, account_id=tg["account_id"], case_id=req["case_id"], request_id=req["request_id"],
                restraint_type=req["action_type"], held_amount=held, start_date=start.isoformat(),
                last_update_date=upd.isoformat(), issuing_authority=req["agency"],
                closure_status=status, released_date=released))
            rid += 1

    # ------------------------------------------------------------ output
    def write(self, out: Path, ledger, tainted):
        out.mkdir(parents=True, exist_ok=True)
        (out / "gt").mkdir(exist_ok=True)
        files = {}

        def w(name, header, rows):
            path = out / name
            with open(path, "w", newline="", encoding="utf-8") as f:
                cw = csv.writer(f, lineterminator="\n")
                cw.writerow(header)
                n = 0
                for row in rows:
                    cw.writerow(["" if v is None else v for v in row])
                    n += 1
            files[name] = dict(rows=n, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

        w("institutions.csv", ["institution_id", "inst_name", "inst_kind", "observable"],
          [(i, n, k, str(o).upper()) for i, n, k, o in INSTITUTIONS])
        obs_inst = set(OBS_BANKS)
        ws, we = fmt_ts(ep(WINDOW_START)), fmt_ts(ep(WINDOW_END))
        acc_rows = []
        for a, v in self.accounts.items():
            o = v["institution_id"] in obs_inst
            opening = f"{v['opening']:.2f}" if o and a not in self.missing_opening else None
            acc_rows.append((a, v["institution_id"], v["holder_label"], v["acct_type"], v["opened_date"],
                             opening, ws if o else None, ep(WINDOW_START) if o else None,
                             f"{self.final_balance.get(a, 0.0):.2f}" if o else None, we if o else None))
        w("accounts.csv", ["account_id", "institution_id", "holder_label", "acct_type", "opened_date",
                           "opening_balance", "opening_ts", "opening_epoch", "closing_balance", "closing_ts"], acc_rows)
        # Analysis view of transactions: only rows a reviewer could hold (at least
        # one observable side), minus deleted records, plus duplicates and skew.
        obs_acc = {a for a, v in self.accounts.items() if v["institution_id"] in obs_inst}
        rows = []
        for t in self.txns:
            if t["txn_id"] in self.deleted_txns:
                continue
            if t["frm"] not in obs_acc and t["to"] not in obs_acc:
                continue
            e = self.skewed.get(t["txn_id"], t["epoch"])
            rows.append((t["txn_id"], t["seq"], fmt_ts(e), e, t["frm"], t["to"], f"{t['amount']:.2f}",
                         t["channel"], t["ref"], t["status"], t["reversal_of"]))
        for i, t in enumerate(self.dup_rows, 1):
            e = t["epoch"] + self.rng.randint(1, 40)
            rows.append((f"D{i:010d}", self.seq + i, fmt_ts(e), e, t["frm"], t["to"], f"{t['amount']:.2f}",
                         t["channel"], t["ref"], "COMPLETED", None))
        self.rng.shuffle(rows)   # out-of-order records: file order carries no meaning
        w("transactions.csv", ["txn_id", "seq_id", "ts", "ts_epoch", "from_acct", "to_acct", "amount", "channel",
                               "txn_ref", "txn_status", "reversal_of"], rows)
        w("cases.csv", ["case_id", "case_ref", "victim_account", "reported_loss", "fraud_ts", "fraud_epoch"],
          [(c["case_id"], c["case_ref"], c["victim"], f"{c['loss']:.2f}", fmt_ts(c["fraud"]), c["fraud"])
           for c in self.cases])
        w("case_disputed_txns.csv", ["case_id", "txn_id"], [(c, t) for t, c in self.disputed.items()])
        w("requests.csv", ["request_id", "case_id", "received_ts", "received_epoch", "issuing_officer", "designation",
                           "agency", "agency_contact", "case_reference", "legal_provision", "action_type",
                           "stated_amount", "quoted_txn_id"],
          [(q["request_id"], q["case_id"], fmt_ts(q["received"]), q["received"], q["officer"], q["designation"],
            q["agency"], q["contact"], q["case_reference"], q["legal_provision"], q["action_type"],
            q["stated_amount"], q["quoted_txn_id"]) for q in self.requests])
        w("request_targets.csv", ["request_id", "account_id", "requested_scope", "requested_amount", "quoted_txn_id"],
          [(t["request_id"], t["account_id"], t["scope"], t["amount"], t["quoted_txn_id"]) for t in self.targets])
        w("restraints.csv", ["restraint_id", "account_id", "case_id", "request_id", "restraint_type", "held_amount",
                             "start_date", "last_update_date", "issuing_authority", "closure_status", "released_date"],
          [tuple(x.values()) for x in self.restraints])
        w("checklist_items.csv", ["item_code", "field_name", "label", "required", "sort_order"], [
            ("OFFICER", "issuing_officer", "Issuing officer's name", "TRUE", 1),
            ("DESIGNATION", "designation", "Officer's designation", "TRUE", 2),
            ("CONTACT", "agency_contact", "Agency contact details", "TRUE", 3),
            ("CASE_REF", "case_reference", "FIR / crime / NCRP / CFCFRMS reference", "TRUE", 4),
            ("LEGAL_PROVISION", "legal_provision", "Legal provision invoked", "TRUE", 5),
            ("TXN", "quoted_txn_id", "Disputed transaction details", "TRUE", 6),
            ("AMOUNT", "stated_amount", "Disputed amount", "TRUE", 7),
            ("ACTION", "action_type", "Type of action sought", "TRUE", 8),
        ])
        w("gt/case_scenario.csv", ["case_id", "scenario"], sorted(self.scenario.items()))
        w("gt/chain_txns.csv", ["case_id", "txn_id", "layer"], self.chain)
        w("gt/ledger.csv", ["case_id", "account_id", "convention", "retained"],
          [(c, a, k, f"{v:.6f}") for c, a, k, v in ledger])
        planted = list(self.planted) + [("UNDETERMINABLE", c, None, a, None,
                                         "planted, or downstream of a planted record defect")
                                        for c, a in sorted(tainted)]
        w("gt/planted_defects.csv", ["defect_type", "case_id", "request_id", "account_id", "txn_id", "detail"], planted)
        return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default="data/L")
    a = ap.parse_args()
    t0 = time.time()
    g = Gen(a.scale, a.seed)
    g.build_population()
    print(f"[gen] accounts {len(g.accounts):,}", flush=True)
    g.background_events()
    g.build_cases()
    print(f"[gen] events queued {len(g.events):,}, cases {len(g.cases):,}", flush=True)
    g.simulate()
    print(f"[gen] transactions {len(g.txns):,} ({time.time() - t0:.0f}s)", flush=True)
    g.build_requests()
    g.plant_record_defects()
    true = g.netted_true_txns()
    obs = {x for x, v in g.accounts.items() if v["institution_id"] in OBS_BANKS}
    probes_req = defaultdict(list)
    for tg in g.targets:
        probes_req[tg["request_id"]].append(tg["account_id"])
    ledger, probes, tainted, carried, dust = build_ledger(
        accounts={x: v["opening"] for x, v in g.accounts.items()},
        txns=true, cases=[c["case_id"] for c in g.cases], ref_epoch={c["case_id"]: c["ref"] for c in g.cases},
        disputed=g.disputed, observable=obs, tainted_accounts=g.tainted_accounts,
        balance_probes=probes_req)
    print(f"[gen] ground-truth ledger rows {len(ledger):,} ({time.time() - t0:.0f}s)", flush=True)
    g.plant_request_defects(probes)
    g.build_restraints(probes)
    files = g.write(Path(a.out), ledger, tainted)
    manifest = dict(generator_version=GENERATOR_VERSION, seed=a.seed, scale=a.scale,
                    generated_at=datetime.now().isoformat(timespec="seconds"), files=files,
                    snapshot_id="sha256:" + hashlib.sha256(
                        json.dumps({k: v["sha256"] for k, v in files.items()}, sort_keys=True).encode()
                    ).hexdigest()[:32])
    (Path(a.out) / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"[gen] done in {time.time() - t0:.0f}s -> {a.out}")
    for k, v in files.items():
        print(f"   {k:28s} {v['rows']:>10,}")


if __name__ == "__main__":
    main()
