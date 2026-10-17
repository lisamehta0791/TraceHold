"""Self-contained, printable HTML rendering of an evidence packet."""
from __future__ import annotations

import html

from app.texts import inr

STATUS_LABEL = {"DETERMINED": "Determined", "RANGE": "Range (assumption-dependent)",
                "UNDETERMINABLE": "Undeterminable", "OUT_OF_SCOPE": "Out of observable scope"}
CLASS_LABEL = {"WITHIN_EVIDENCE": "Within evidence", "WITHIN_RANGE": "Within range, assumption-dependent",
               "EXCEEDS_EVIDENCE": "Exceeds evidence", "CANNOT_DETERMINE": "Cannot determine"}


def e(x) -> str:
    return html.escape("" if x is None else str(x))


def pct(x) -> str:
    return "—" if x is None else f"{100 * float(x):.1f}%"


def ratio_txt(r: dict) -> str:
    return f" ({float(r['ratio_to_upper']):.2f}×)" if r.get("ratio_to_upper") else ""


def render_packet(p: dict) -> str:
    h, req, rep = p["header"], p.get("request") or {}, p["reproducibility"]
    comp = (req.get("completeness") or {})
    rows_sizing = "".join(
        f"<tr><td class=mono>{e(n['account_id'])}</td><td>{e(n.get('layer'))}</td><td class=num>{inr(n.get('balance'))}</td>"
        f"<td class=num>{inr(n.get('retained_pr'))}</td><td class=num>{inr(n.get('retained_fifo'))}</td>"
        f"<td class=num>{inr(n.get('retained_lifo'))}</td>"
        f"<td class=num>{'—' if n.get('status') == 'UNDETERMINABLE' else inr(n.get('lower')) + ' – ' + inr(n.get('upper'))}</td>"
        f"<td>{pct(n.get('share_lo'))} – {pct(n.get('share_hi'))}</td>"
        f"<td><span class='chip {e(n.get('status'))}'>{e(STATUS_LABEL.get(n.get('status'), n.get('status')))}</span></td></tr>"
        for n in p["sizing"])
    rows_review = "".join(
        f"<tr><td class=mono>{e(r['account_id'])}</td><td>{e('Whole balance' if r['requested_scope'] == 'WHOLE_BALANCE' else 'Amount')}</td>"
        f"<td class=num>{inr(r.get('requested_amount'))}</td><td class=num>{inr(r.get('lower'))} – {inr(r.get('upper'))}</td>"
        f"<td><b>{e(CLASS_LABEL.get(r['classification'], r['classification']))}</b>"
        f"{ratio_txt(r)}</td>"
        f"<td>{'<br>'.join(e(x) for x in r['reasons'])}</td></tr>"
        for r in p["review"])
    rows_edges = "".join(
        f"<tr><td class=mono>{e(x['txn_id'])}</td><td>{e(x['ts'])}</td><td class=mono>{e(x['from'])}</td>"
        f"<td class=mono>{e(x['to'])}</td><td class=num>{inr(x['amount'])}</td><td class=num>{inr(x['carried_pr'])}</td>"
        f"<td class=num>{inr(x['carried_fifo'])}</td><td class=num>{inr(x['carried_lifo'])}</td><td>{e(x['terminal_state'])}</td></tr>"
        for x in p["edges"][:200])
    rows_cons = "".join(
        f"<tr><td>{e(c['convention'])}</td><td class=num>{inr(c['retained'])}</td><td class=num>{inr(c['exited'])}</td>"
        f"<td class=num>{inr(c['dust'])}</td><td class=num>{inr(c['absorbed'])}</td><td class=num>{inr(c['loss'])}</td>"
        f"<td>{'✓ passed' if c['passed'] else '✗ FAILED'}</td></tr>" for c in p["conservation"])
    rows_ev = "".join(
        f"<tr><td class=mono>{e(x['account_id'])}</td><td>{e(x['figure'])}</td><td class=num>{inr(x['value'])}</td>"
        f"<td class='mono small'>{e(', '.join(x['source_txn_ids'][:30]))}{' …' if len(x['source_txn_ids']) > 30 else ''}</td></tr>"
        for x in p["evidence"] if x["figure"] != "BALANCE_REF")
    checklist = "".join(
        f"<li class='{e(i['kind'])}'><b>{e(i['label'])}</b>: {e(i['detail'])}</li>" for i in comp.get("items", []))
    fwd = "".join(f"<pre>{e(x['draft'])}</pre>" for x in p["forwarded_requests"])
    assumptions = "".join(f"<li>{e(a)}</li>" for a in p["assumptions"])
    missing = "".join(f"<li class=mono>{e(m['account_id'])}: {e('; '.join(m['reasons'] or []))}</li>"
                      for m in p["missing_data"]) or "<li>None</li>"
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>Evidence packet · {e(h['case_ref'])}</title>
<style>
:root {{ --paper:#F4ECDF; --paper2:#EADFCB; --line:#D9C7A8; --ink:#2A1B14; --soft:#5B4636; --ox:#7A2232;
        --terra:#C2553A; --saffron:#E39B2D; --olive:#6E7B3A; --clay:#B98B6A; }}
body {{ background:var(--paper); color:var(--ink); font:14px/1.5 Georgia, 'Times New Roman', serif; margin:0; }}
main {{ max-width:1100px; margin:0 auto; padding:32px 24px 64px; }}
h1 {{ font-size:30px; margin:0; color:var(--ox); letter-spacing:-.01em }}
h2 {{ font-size:18px; border-bottom:2px solid var(--ox); padding-bottom:4px; margin-top:32px; color:var(--ox) }}
.notice {{ background:var(--paper2); border-left:4px solid var(--saffron); padding:10px 14px; margin:16px 0; }}
table {{ width:100%; border-collapse:collapse; font:12.5px/1.4 'Segoe UI', system-ui, sans-serif; }}
th, td {{ border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top }}
th {{ background:var(--paper2); color:var(--soft); font-weight:600 }}
.num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums }}
.mono {{ font-family:Consolas, 'JetBrains Mono', monospace }} .small {{ font-size:11px; color:var(--soft) }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px 24px; font-family:'Segoe UI', sans-serif }}
.grid div span {{ display:block; color:var(--soft); font-size:12px }}
.chip {{ padding:1px 8px; border-radius:10px; font-size:11px; white-space:nowrap; background:var(--paper2) }}
.chip.DETERMINED {{ background:#DDE2C4 }} .chip.RANGE {{ background:#F6DDB0 }} .chip.UNDETERMINABLE {{ background:#E7D3C3 }}
li.MISSING {{ color:var(--terra) }} li.CONFLICT {{ color:var(--ox) }} li.OK {{ color:var(--olive) }}
pre {{ background:var(--paper2); padding:12px; white-space:pre-wrap; font-size:12px; border-radius:6px }}
.repro {{ font:12px Consolas, monospace; color:var(--soft); word-break:break-all }}
@media print {{ body {{ background:#fff }} .notice, th, pre {{ background:#f3f3f3 }} }}
</style></head><body><main>
<h1>Evidence packet</h1>
<div class=small>Case {e(h['case_ref'])} · generated by TraceHold {e(rep.get('software_version'))}</div>
<div class=notice>{e(p['notice'])} Every figure below cites the transaction records it rests on.</div>
<h2>Case header</h2>
<div class=grid>
<div><span>Case reference</span>{e(h['case_ref'])}</div><div><span>Reported loss</span>{inr(h['reported_loss'])}</div>
<div><span>Time of fraud</span>{e(h['fraud_ts'])}</div><div><span>Reference time</span>{e(h['ref_ts'])}</div>
<div><span>Victim account</span><span class=mono style="color:inherit;font-size:14px">{e(h['victim_account'])}</span></div>
<div><span>Request status</span>{e(comp.get('status'))}</div>
</div>
<h2>Request completeness</h2><ul>{checklist}</ul>
<h2>Per-account sizing at the reference time</h2>
<table><tr><th>Account</th><th>Layer</th><th>Balance</th><th>Pro-rata</th><th>FIFO</th><th>LIFO (bound)</th><th>Supported range</th><th>Traceable share</th><th>Status</th></tr>{rows_sizing}</table>
<h2>Scope versus evidence</h2>
<table><tr><th>Account</th><th>Scope</th><th>Requested</th><th>Supported</th><th>Classification</th><th>Reasons</th></tr>{rows_review}</table>
<h2>Trail ({p['trail_summary']['transfers']} transfers carrying disputed funds{', first 200 shown' if p['trail_summary']['transfers'] > 200 else ''})</h2>
<table><tr><th>Transfer</th><th>Time</th><th>From</th><th>To</th><th>Amount</th><th>Pro-rata</th><th>FIFO</th><th>LIFO</th><th>Terminal</th></tr>{rows_edges}</table>
<h2>Conservation check</h2>
<p class=small>Retained + exited + dust + absorbed must equal the reported loss for every convention.</p>
<table><tr><th>Convention</th><th>Retained</th><th>Exited</th><th>Dust</th><th>Absorbed</th><th>Loss</th><th>Result</th></tr>{rows_cons}</table>
<h2>Assumptions and conventions</h2><ul>{assumptions}</ul>
<h2>Missing data and unresolved questions</h2><ul>{missing}</ul>
<h2>Source records behind each figure</h2>
<table><tr><th>Account</th><th>Figure</th><th>Value</th><th>Transaction records</th></tr>{rows_ev}</table>
{'<h2>Forwarded-request drafts</h2>' + fwd if fwd else ''}
<h2>Reproducibility</h2>
<div class=repro>run {e(rep.get('run_id'))} · snapshot {e(rep.get('snapshot_id'))} · run checksum {e(rep.get('run_checksum'))}<br>
packet checksum {e(rep.get('packet_checksum'))} · run finished {e(rep.get('run_finished'))}<br>config {e(rep.get('config'))}</div>
</main></body></html>"""
