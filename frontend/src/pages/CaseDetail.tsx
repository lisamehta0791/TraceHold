import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../api';
import type { CaseDetail as CD, Convention, Extraction, ReviewRow, RewordResult, TrailNode } from '../types';
import { LetterReview } from '../components/LetterReview';
import { BasisPanel } from '../components/BasisPanel';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { ClassChip, ReqChip, ScenarioChip, StatusChip } from '../components/Chip';
import { ErrorCard } from '../components/ErrorCard';
import {
  IconAlert, IconCheck, IconChevronLeft, IconConflict, IconCopy, IconDoc, IconDownload, IconExternal, IconLetter, IconSpark, IconUser,
} from '../components/Icons';
import { Modal } from '../components/Modal';
import { RangeBar } from '../components/RangeBar';
import { PageSkeleton, RowsSkeleton, Skeleton } from '../components/Skeleton';
import { Tabs } from '../components/Tabs';
import { CalcTimeline } from '../components/CalcTimeline';
import { BAR_RADIUS, ChartTip, Legend, axisProps, gridProps } from '../components/charts';
import { copyText, downloadText } from '../lib/download';
import {
  C, CONV_COLOR, dateTime, humanize, pct, ratio, rupees, rupees0, rupeesCompact, timeOnly,
} from '../lib/format';
import { riseIn, staggerParent } from '../lib/motion';
import { useAsync } from '../lib/useAsync';

export default function CaseDetail() {
  const { id = '' } = useParams();
  const { data, error, reload } = useAsync(() => api.caseDetail(id), [id]);
  if (error) return <ErrorCard error={error} onRetry={reload} title={`Case ${id} could not be loaded`} />;
  if (!data) return <PageSkeleton tiles={0} panels={2} />;
  return <CaseView key={data.case.case_id} d={data} />;
}

function defaultSelection(d: CD): string | null {
  const req = d.nodes.filter((n) => n.requested_amount !== null && n.observable && !n.is_victim);
  const pick = req.sort((a, b) => (b.ratio_to_upper ?? 0) - (a.ratio_to_upper ?? 0))[0]
    ?? d.nodes.find((n) => !n.is_victim && n.observable);
  return pick?.account_id ?? null;
}

function CaseView({ d }: { d: CD }) {
  const [sel, setSel] = useState<string | null>(() => defaultSelection(d));
  const [tab, setTab] = useState('how');
  const [pktBusy, setPktBusy] = useState(false);
  const node = d.nodes.find((n) => n.account_id === sel) ?? null;
  const review = d.review.find((r) => r.account_id === sel) ?? null;
  const c = d.case;

  const downloadPacket = async () => {
    setPktBusy(true);
    try {
      const p = await api.packet(c.case_id);
      downloadText(`tracehold-packet-${c.case_ref}.json`, JSON.stringify(p, null, 2), 'application/json');
    } catch (e) {
      alert(`Could not fetch the packet: ${(e as Error).message}`);
    } finally { setPktBusy(false); }
  };

  const tabs = [
    { key: 'how', label: 'How it was calculated' },
    { key: 'basis', label: 'What it is based on' },
    { key: 'request', label: 'Request check', badge: d.request?.completeness.items.filter((i) => i.kind !== 'OK').length || undefined },
    { key: 'trail', label: 'Money path', badge: d.edges.length },
    { key: 'dilution', label: 'Layer dilution' },
    { key: 'scope', label: 'Scope review', badge: d.review.filter((r) => r.classification === 'EXCEEDS_EVIDENCE').length || undefined },
    { key: 'forwarded', label: 'Forwarded requests', badge: d.forwarded.length || undefined },
    { key: 'conservation', label: 'Conservation' },
    { key: 'assumptions', label: 'Assumptions' },
  ];

  return (
    <motion.div variants={staggerParent} initial="hidden" animate="show">
      <motion.div variants={riseIn} className="page-head" style={{ alignItems: 'flex-start' }}>
        <div>
          <Link to="/cases" className="row small" style={{ gap: 4, textDecoration: 'none', marginBottom: 8 }}><IconChevronLeft size={14} /> All cases</Link>
          <h1 className="mono" style={{ fontFamily: 'var(--f-display)', fontSize: '1.9rem' }}>{c.case_ref}</h1>
          <div className="row wrap mt" style={{ gap: 18 }}>
            <Meta k="Reported loss" v={<span className="num">{rupees(c.reported_loss)}</span>} />
            <Meta k="Fraud time" v={dateTime(c.fraud_ts)} />
            <Meta k="Reference time" v={<>{dateTime(c.ref_ts)} <span className="mute2 tiny">({humanize(c.ref_rule)})</span></>} />
            <Meta k="Victim account" v={<span className="mono">{c.victim_account}</span>} />
          </div>
          <div className="row wrap mt" style={{ gap: 8 }}>
            <ScenarioChip s={c.scenario} />
            {d.request && <ReqChip s={d.request.completeness.status} />}
          </div>
        </div>
        <div className="row wrap">
          <Button variant="primary" icon={<IconExternal size={16} />} href={api.packetHtmlUrl(c.case_id)} target="_blank">Open evidence packet</Button>
          <Button icon={<IconDownload size={16} />} loading={pktBusy} onClick={downloadPacket}>Download packet JSON</Button>
        </div>
      </motion.div>


      <motion.div variants={riseIn} className="case-grid">
        <div className="card" style={{ height: 560, display: 'flex', flexDirection: 'column', padding: '14px 0 0' }}>
          <div className="row between" style={{ padding: '0 18px 10px' }}>
            <h3 style={{ margin: 0 }}>Accounts the money reached</h3>
            <span className="tiny muted">Click an account to see its figures</span>
          </div>
          <SizingTab d={d} sel={sel} onSel={setSel} />
        </div>
        <AccountPanel caseId={c.case_id} node={node} review={review} />
      </motion.div>

      <motion.div variants={riseIn} className="card mt" style={{ paddingTop: 6 }}>
        <Tabs tabs={tabs} value={tab} onChange={setTab} />
        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.22 }} style={{ paddingTop: 16 }}>
            <ErrorBoundary compact key={tab + (sel ?? '')}>
            {tab === 'how' && <HowTab caseId={c.case_id} sel={sel} d={d} />}
            {tab === 'basis' && <BasisTab caseId={c.case_id} />}
            {tab === 'request' && <RequestTab d={d} />}
            {tab === 'trail' && <TrailTab d={d} sel={sel} onSel={setSel} />}
            {tab === 'dilution' && <DilutionTab d={d} />}
            {tab === 'scope' && <ScopeTab d={d} onSel={setSel} />}
            {tab === 'forwarded' && <ForwardedTab d={d} />}
            {tab === 'conservation' && <ConservationTab d={d} />}
            {tab === 'assumptions' && <AssumptionsTab d={d} />}
            </ErrorBoundary>
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}

const Meta = ({ k, v }: { k: string; v: React.ReactNode }) => (
  <div><div className="eyebrow" style={{ fontSize: 10 }}>{k}</div><div className="small" style={{ fontWeight: 560 }}>{v}</div></div>
);

// ------------------------------------------------------------- side panel
function AccountPanel({ caseId, node, review }: { caseId: number; node: TrailNode | null; review: ReviewRow | null }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card hi" style={{ height: 560, overflow: 'auto' }}>
      <AnimatePresence mode="wait">
        {!node ? (
          <motion.p key="none" className="muted small" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>Select an account in the list to see its figures.</motion.p>
        ) : (
          <motion.div key={node.account_id} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} transition={{ duration: 0.25 }} className="stack" style={{ gap: 12 }}>
            <div>
              <div className="eyebrow">{node.is_victim ? 'Victim account' : !node.observable ? `Layer ${node.layer} · account at another bank` : `Layer ${node.layer} · ${humanize(node.account_type)}`}</div>
              <h2 className="mono" style={{ fontFamily: 'var(--f-mono)', fontSize: '1.2rem', marginTop: 2 }}>{node.account_id}</h2>
              <div className="small muted">{node.institution}{!node.observable && ' · outside observable institutions'}</div>
            </div>
            <div className="row wrap" style={{ gap: 6 }}>
              <StatusChip status={node.status} />
              {!node.is_victim && <ClassChip c={node.classification} />}
            </div>
            {node.status_reasons.length > 0 && (
              <ul className="clean tiny muted stack" style={{ gap: 2 }}>{node.status_reasons.map((r) => <li key={r}>· {r}</li>)}</ul>
            )}
            {node.is_victim ? (
              <p className="small muted">This is where the reported loss originated. Sizing applies to the receiving accounts.</p>
            ) : !node.observable ? (
              <div className="note"><span>Records for this destination are not available. No amount is sized here; a forwarded request can be drafted instead (see the “Forwarded requests” tab).</span></div>
            ) : (
              <>
                <div className="grid g2" style={{ gap: 10 }}>
                  <Fig k="Balance at reference time" v={rupees(node.balance)} />
                  <Fig k="Traceable share" v={`${pct(node.share_lo)} – ${pct(node.share_hi)}`} />
                </div>
                <div className="well" style={{ padding: '10px 12px' }}>
                  <div className="eyebrow" style={{ marginBottom: 6 }}>Retained disputed money</div>
                  {(['PR', 'FIFO', 'LIFO'] as Convention[]).map((k) => (
                    <div key={k} className="row between small" style={{ padding: '2px 0', fontWeight: k === 'LIFO' ? 450 : 600 }}>
                      <span className="row gap-s"><i style={{ width: 12, height: 3, borderRadius: 2, background: CONV_COLOR[k], display: 'inline-block' }} />{k === 'PR' ? 'Pro-rata' : k === 'LIFO' ? 'LIFO (bounding case)' : 'FIFO'}</span>
                      <span className="num">{rupees(k === 'PR' ? node.retained_pr : k === 'FIFO' ? node.retained_fifo : node.retained_lifo)}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="row between small"><span className="muted">Supported range</span><b className="num">{rupees(node.lower)} – {rupees(node.upper)}</b></div>
                  <RangeBar lower={node.lower} upper={node.upper} lowerExt={node.lower_ext} upperExt={node.upper_ext} requested={node.requested_amount}
                    markers={{ PR: node.retained_pr, FIFO: node.retained_fifo, LIFO: node.retained_lifo }} height={12} showLegend />
                </div>
                {node.requested_amount !== null && (
                  <div className="row between small">
                    <span className="muted">Requested ({node.requested_scope === 'WHOLE_BALANCE' ? 'whole balance' : 'amount'})</span>
                    <span><b className="num">{rupees(node.requested_amount)}</b> <span className="mute2">· {ratio(node.ratio_to_upper)} upper</span></span>
                  </div>
                )}
              </>
            )}
            {node.combined && (
              <div className="note" style={{ padding: '8px 12px' }}>
                <span className="small">
                  This account is in <b>{node.combined.cases}</b> cases. Each case is sized separately;
                  {node.combined.upper != null
                    ? <> combined over all of them the records support <b className="num">{rupees(node.combined.lower)} – {rupees(node.combined.upper)}</b>.</>
                    : <> a combined figure cannot be stated because one of the cases is undeterminable.</>}
                </span>
              </div>
            )}
            {review && (
              <div>
                <div className="eyebrow" style={{ marginBottom: 4 }}>Facts for an exceptional case</div>
                <p className="tiny mute2" style={{ marginBottom: 6 }}>Facts, not a score. They do not imply wrongdoing.</p>
                <ul className="clean small stack" style={{ gap: 3 }}>
                  <li>· Appears in <b>{review.facts.cases_through_account}</b> case{review.facts.cases_through_account === 1 ? '' : 's'}</li>
                  <li>· <b>{pct(review.facts.share_moved_within_minutes, 0)}</b> of credits moved on within {review.facts.minutes_window} minutes</li>
                  <li>· Commingling: <b>{pct(review.facts.commingling, 1)}</b> of the balance is other funds (pro-rata)</li>
                  <li>· Disputed funds {review.facts.separable ? <b>can</b> : <b>cannot</b>} be separated unambiguously</li>
                </ul>
              </div>
            )}
            {!node.is_victim && node.observable && (
              <Button icon={<IconUser size={15} />} onClick={() => setOpen(true)}>Plain-language explanation for the account holder</Button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
      {node && <ExplanationModal open={open} onClose={() => setOpen(false)} caseId={caseId} account={node.account_id} />}
    </div>
  );
}

const Fig = ({ k, v }: { k: string; v: string }) => (
  <div><div className="tiny mute2">{k}</div><div className="num" style={{ fontWeight: 600 }}>{v}</div></div>
);

function ExplanationModal({ open, onClose, caseId, account }: { open: boolean; onClose: () => void; caseId: number; account: string }) {
  const [text, setText] = useState<string | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [n, setN] = useState(0);
  const [rw, setRw] = useState<RewordResult | null>(null);
  const [rwBusy, setRwBusy] = useState(false);
  const [rwErr, setRwErr] = useState<Error | null>(null);
  const [show, setShow] = useState<'template' | 'ai'>('template');
  useEffect(() => {
    if (!open) return;
    setText(null); setErr(null); setRw(null); setRwErr(null); setShow('template');
    api.explanation(caseId, account).then((e) => setText(e.text)).catch((e: Error) => setErr(e));
  }, [open, caseId, account, n]);
  const reword = async () => {
    setRwBusy(true); setRwErr(null);
    try {
      const r = await api.reword(caseId, account); setRw(r); setShow(r.used === 'AI' ? 'ai' : 'template');
      document.querySelector('.modal')?.scrollTo({ top: 0, behavior: 'smooth' });
    }
    catch (e) { setRwErr(e as Error); } finally { setRwBusy(false); }
  };
  const shown = show === 'ai' && rw?.used === 'AI' ? rw.reworded : text;
  return (
    <Modal open={open} onClose={onClose} title="For the account holder"
      footer={shown ? <>
        <Button size="sm" icon={<IconSpark size={14} />} loading={rwBusy} onClick={reword} disabled={!!rw}>Reword with AI (checked)</Button>
        <CopyButton text={shown} />
        <Button icon={<IconDownload size={15} />} onClick={() => downloadText(`explanation-${account}.txt`, shown)}>Download .txt</Button>
      </> : null}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>Account {account}</div>
      {rw && (
        <div className={`note ${rw.check.ok ? 'olive' : ''}`} style={{ marginBottom: 10 }}>
          {rw.check.ok ? <IconCheck size={15} /> : <IconAlert size={15} />}
          <span className="small">
            {rw.check.ok
              ? <>Reworded by {rw.model}. The check confirmed all {rw.check.facts_checked} amounts, dates and references are unchanged and nothing was added.</>
              : <>The AI's rewording failed the check ({rw.check.problems.join('; ')}), so the original letter is kept.</>}
            {rw.check.ok && (
              <span className="row" style={{ gap: 6, marginTop: 6 }}>
                <button className={`chip-btn ${show === 'ai' ? 'on' : ''}`} onClick={() => setShow('ai')}>Reworded</button>
                <button className={`chip-btn ${show === 'template' ? 'on' : ''}`} onClick={() => setShow('template')}>Original</button>
              </span>
            )}
          </span>
        </div>
      )}
      {rwErr && <div style={{ marginBottom: 10 }}><ErrorCard error={rwErr} title="Rewording is not available" /></div>}
      {err ? <ErrorCard error={err} onRetry={() => setN((x) => x + 1)} title="Explanation unavailable" />
        : !shown ? <div className="stack"><Skeleton h={14} /><Skeleton h={14} w="92%" /><Skeleton h={14} w="80%" /><Skeleton h={14} w="88%" /></div>
          : <div className="letter">{shown}</div>}
    </Modal>
  );
}

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button size="sm" icon={done ? <IconCheck size={15} /> : <IconCopy size={15} />} onClick={async () => { await copyText(text); setDone(true); setTimeout(() => setDone(false), 1600); }}>
      {done ? 'Copied' : label}
    </Button>
  );
}

// ------------------------------------------------------------- tabs
function RequestTab({ d }: { d: CD }) {
  const r = d.request;
  if (!r) return <p className="muted">No request is linked to this case.</p>;
  const icon = (k: string) =>
    k === 'OK' ? <span className="check-icon" style={{ background: C.olive }}><IconCheck size={14} /></span>
      : k === 'MISSING' ? <span className="check-icon" style={{ background: C.saffron, color: C.ink }}><IconAlert size={14} /></span>
        : <span className="check-icon" style={{ background: C.terracotta }}><IconConflict size={14} /></span>;
  return (
    <div className="grid g2">
      <div>
        <div className="row between" style={{ marginBottom: 6 }}>
          <h3>Completeness check</h3>
          <ReqChip s={r.completeness.status} />
        </div>
        <div className="small muted" style={{ marginBottom: 8 }}>
          Received {dateTime(r.received_ts)} · {humanize(r.action_type)} · stated {rupees(r.stated_amount)}
        </div>
        <motion.div variants={staggerParent} initial="hidden" animate="show">
          {r.completeness.items.map((it) => (
            <motion.div key={it.code} className="check-item" variants={{ hidden: { opacity: 0, x: -12 }, show: { opacity: 1, x: 0 } }}>
              <motion.span variants={{ hidden: { scale: 0 }, show: { scale: 1, transition: { type: 'spring', stiffness: 500, damping: 20 } } }}>{icon(it.kind)}</motion.span>
              <div>
                <div style={{ fontWeight: 600 }}>{it.label} <span className="tiny mute2">{it.kind === 'OK' ? '' : it.kind === 'MISSING' ? '· missing' : '· conflict'}</span></div>
                <div className="small muted">{it.detail}</div>
              </div>
            </motion.div>
          ))}
        </motion.div>
        <div className="grid g2 mt small" style={{ gap: 8 }}>
          <Fieldv k="Issuing officer" v={r.issuing_officer} /><Fieldv k="Designation" v={r.designation} />
          <Fieldv k="Agency" v={r.agency} /><Fieldv k="Contact" v={r.agency_contact} />
          <Fieldv k="Case reference" v={r.case_reference} /><Fieldv k="Legal provision" v={r.legal_provision} />
        </div>
      </div>
      <div>
        <div className="row between" style={{ marginBottom: 8 }}>
          <h3>Clarification draft</h3>
          {r.completeness.clarification_draft && <CopyButton text={r.completeness.clarification_draft} />}
        </div>
        {r.completeness.clarification_draft
          ? <pre className="draft">{r.completeness.clarification_draft}</pre>
          : <div className="note olive"><span>The request is complete — no clarification needed.</span></div>}
        <p className="tiny mute2 mt">Draft only. Nothing is sent automatically; a person reviews and sends it.</p>
      </div>
      <CaseLetter d={d} />
    </div>
  );
}

function CaseLetter({ d }: { d: CD }) {
  const { data } = useAsync(() => api.caseLetter(d.case.case_id), [d.case.case_id]);
  const [ex, setEx] = useState<Extraction | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const letter = data?.letter;
  if (!letter) return null;
  const r = d.request;
  const record: Record<string, string | null> = r ? {
    officer: r.issuing_officer, designation: r.designation, agency: r.agency, contact: r.agency_contact,
    case_reference: r.case_reference, legal_provision: r.legal_provision,
    stated_amount: r.stated_amount != null ? String(r.stated_amount) : null, action_type: r.action_type,
  } : {};
  const read = async () => {
    setBusy(true); setErr(null);
    try { setEx(await api.extract(letter.body, { case_id: d.case.case_id }, letter.doc_id)); }
    catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  return (
    <div className="span2" style={{ gridColumn: '1 / -1', marginTop: 8 }}>
      <div className="row between wrap" style={{ marginBottom: 8, gap: 10 }}>
        <h3 className="row" style={{ gap: 8 }}><IconLetter size={17} /> The letter as received (synthetic free text)</h3>
        {!ex && <Button size="sm" variant="primary" icon={<IconSpark size={14} />} loading={busy} onClick={read}>Read with AI and compare</Button>}
      </div>
      {!ex && <pre className="draft" style={{ maxHeight: 260 }}>{letter.body}</pre>}
      {err && <ErrorCard error={err} title="The letter could not be read" />}
      {ex && <LetterReview ex={ex} recordValues={record} confirmLabel="Confirm fields"
        onConfirm={async (f, by) => { await api.confirmExtraction(ex.extraction_id, f, by); }} />}
    </div>
  );
}
const Fieldv = ({ k, v }: { k: string; v: string | null }) => (
  <div><div className="tiny mute2">{k}</div><div style={{ color: v ? C.ink : C.terracotta }}>{v ?? 'Not stated'}</div></div>
);

function TrailTab({ d, sel, onSel }: { d: CD; sel: string | null; onSel: (s: string) => void }) {
  return (
    <div className="table-wrap" style={{ maxHeight: 460 }}>
      <table className="ledger">
        <thead><tr><th>Txn</th><th>Time</th><th>From</th><th>To</th><th>Channel</th><th className="r">Layer</th><th className="r">Amount</th>
          <th className="r">Pro-rata</th><th className="r">FIFO</th><th className="r">LIFO</th><th>Terminal</th><th>Flags</th></tr></thead>
        <tbody>
          {d.edges.map((e) => (
            <tr key={e.txn_id} className={`clickable ${sel === e.to || sel === e.from ? 'sel' : ''}`} onClick={() => onSel(e.to)}>
              <td className="mono small">{e.txn_id}</td><td className="small">{timeOnly(e.ts)}</td>
              <td className="mono small">{e.from}</td><td className="mono small">{e.to}</td><td className="small">{e.channel}</td>
              <td className="r num">{e.layer}</td><td className="r num">{rupees(e.amount)}</td>
              <td className="r num">{rupees(e.carried_pr)}</td><td className="r num">{rupees(e.carried_fifo)}</td><td className="r num">{rupees(e.carried_lifo)}</td>
              <td>{e.terminal_state === 'INTERNAL' ? <span className="tiny mute2">internal</span> : <span className="chip plain">{humanize(e.terminal_state)}</span>}</td>
              <td className="tiny">{e.flags.join(', ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SizingTab({ d, sel, onSel }: { d: CD; sel: string | null; onSel: (s: string) => void }) {
  const rows = d.nodes.filter((n) => !n.is_victim && (n as { kind?: string }).kind !== 'SINK');
  const max = Math.max(1, ...rows.map((n) => Math.max(n.upper_ext, n.requested_amount ?? 0)));
  return (
    <div className="table-wrap" style={{ flex: 1, minHeight: 0 }}>
      <table className="ledger">
        <thead><tr><th>Account</th><th className="r">Layer</th><th className="r">Balance</th><th className="r">Pro-rata</th><th className="r">FIFO</th><th className="r">LIFO</th>
          <th style={{ minWidth: 180 }}>Range</th><th className="r">Share</th><th>Status</th><th>Classification</th><th className="r">Whole ÷ upper</th></tr></thead>
        <tbody>
          {rows.map((n) => (
            <tr key={n.account_id} className={`clickable ${sel === n.account_id ? 'sel' : ''}`} onClick={() => onSel(n.account_id)}>
              <td className="mono small">{n.account_id}</td><td className="r num">{n.layer}</td><td className="r num">{rupees(n.balance)}</td>
              <td className="r num">{rupees(n.retained_pr)}</td><td className="r num">{rupees(n.retained_fifo)}</td><td className="r num">{rupees(n.retained_lifo)}</td>
              <td><RangeBar compact lower={n.lower} upper={n.upper} requested={n.requested_amount} max={max} height={7} /><div className="tiny num mute2">{n.observable ? `${rupees0(n.lower)} – ${rupees0(n.upper)}` : 'records not available'}</div></td>
              <td className="r num small">{pct(n.share_lo)}–{pct(n.share_hi)}</td>
              <td><StatusChip status={n.status} title={(n.status_reasons ?? []).join('; ')} /></td>
              <td><ClassChip c={n.classification} /></td>
              <td className="r num">{n.balance > 0 && n.upper > 0 ? ratio(n.balance / n.upper) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DilutionTab({ d }: { d: CD }) {
  return (
    <div className="grid g3">
      <div className="span2">
        <div className="row between" style={{ marginBottom: 8 }}>
          <h3>Average traceable share by layer</h3>
          <Legend items={[{ label: 'Pro-rata', color: C.oxblood }, { label: 'FIFO', color: C.saffron }]} />
        </div>
        <div style={{ height: 280 }}>
          <ResponsiveContainer>
            <BarChart data={d.dilution} margin={{ top: 10, right: 10, left: -6, bottom: 0 }} barGap={2} barCategoryGap="28%">
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="layer" {...axisProps} tickFormatter={(l) => `Layer ${l}`} />
              <YAxis {...axisProps} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} width={46} />
              <Tooltip content={<ChartTip fmt={(v) => pct(v)} labelFmt={(l) => `Layer ${l}`} />} cursor={{ fill: 'rgba(205,180,138,0.18)' }} />
              <Bar dataKey="share_pr" name="Pro-rata" fill={C.oxblood} radius={BAR_RADIUS} maxBarSize={24} animationDuration={800} />
              <Bar dataKey="share_fifo" name="FIFO" fill={C.saffron} radius={BAR_RADIUS} maxBarSize={24} animationDuration={800} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div>
        <h3 style={{ marginBottom: 8 }}>By layer</h3>
        <table className="ledger">
          <thead><tr><th>Layer</th><th className="r">Accounts</th><th className="r">PR</th><th className="r">FIFO</th><th className="r">Below 5%</th></tr></thead>
          <tbody>{d.dilution.map((l) => (
            <tr key={l.layer}><td>{l.layer}</td><td className="r num">{l.n_accounts}</td><td className="r num">{pct(l.share_pr)}</td><td className="r num">{pct(l.share_fifo)}</td><td className="r num">{l.below_threshold}</td></tr>
          ))}</tbody>
        </table>
        <p className="tiny mute2 mt">Accounts below the threshold hold so little traceable money that a hold is hard to justify on these records.</p>
      </div>
    </div>
  );
}

function ScopeTab({ d, onSel }: { d: CD; onSel: (s: string) => void }) {
  if (!d.review.length) return <p className="muted">No accounts were named in the request.</p>;
  const rows = [...d.review].sort((a, b) => (b.ratio_to_upper ?? 0) - (a.ratio_to_upper ?? 0));
  const max = Math.max(1, ...rows.map((r) => Math.max(r.upper, r.requested_amount ?? 0)));
  return (
    <motion.div className="stack" style={{ gap: 12 }} variants={staggerParent} initial="hidden" animate="show">
      {rows.map((r) => (
        <Card key={r.account_id} onClick={() => onSel(r.account_id)}>
          <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 220px', gap: 18, alignItems: 'center' }}>
            <div>
              <div className="mono" style={{ fontWeight: 600 }}>{r.account_id}</div>
              <div className="row wrap" style={{ gap: 6, marginTop: 4 }}><ClassChip c={r.classification} /></div>
            </div>
            <div>
              <RangeBar lower={r.lower} upper={r.upper} requested={r.requested_amount} max={max} />
              <div className="tiny muted">{r.reasons.join(' · ')}</div>
            </div>
            <div className="small" style={{ textAlign: 'right' }}>
              <div>Requested <b className="num">{rupees(r.requested_amount)}</b></div>
              <div className="muted">Supported <span className="num">{rupeesCompact(r.lower)}–{rupeesCompact(r.upper)}</span></div>
              <div className="num" style={{ color: (r.ratio_to_upper ?? 0) > 1.05 ? C.terracotta : C.olive, fontWeight: 650 }}>{ratio(r.ratio_to_upper)} upper bound</div>
            </div>
          </div>
        </Card>
      ))}
    </motion.div>
  );
}

function ForwardedTab({ d }: { d: CD }) {
  if (!d.forwarded.length) return <p className="muted">No money left the observable institutions in this trail.</p>;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="note"><span>Money that left the observable institutions cannot be sized here. These drafts tell the receiving institution what the records show — they are not freeze instructions.</span></div>
      {d.forwarded.map((f) => (
        <div key={f.txn_id} className="grid g2" style={{ alignItems: 'start' }}>
          <div className="stack" style={{ gap: 6 }}>
            <div className="row between"><b className="mono">{f.destination_account}</b><span className="small muted">{f.destination_institution}</span></div>
            <div className="small muted">{f.txn_id} · {f.reference} · {dateTime(f.ts)}</div>
            <div className="small">Amount <b className="num">{rupees(f.amount)}</b></div>
            <div className="row wrap small" style={{ gap: 14 }}>
              {(['PR', 'FIFO', 'LIFO'] as Convention[]).map((k) => (
                <span key={k} className="row gap-s"><i style={{ width: 12, height: 3, background: CONV_COLOR[k], borderRadius: 2, display: 'inline-block' }} />{k === 'PR' ? 'Pro-rata' : k} <span className="num">{rupeesCompact(k === 'PR' ? f.carried_pr : k === 'FIFO' ? f.carried_fifo : f.carried_lifo)}</span></span>
              ))}
            </div>
            {f.checklist_missing.length > 0 && <div className="row wrap" style={{ gap: 6 }}><span className="tiny mute2">Missing:</span>{f.checklist_missing.map((m) => <span key={m} className="chip tint" style={{ ['--c' as string]: C.saffron } as React.CSSProperties}><span className="dot" />{humanize(m)}</span>)}</div>}
            <div className="row" style={{ marginTop: 6 }}>
              <CopyButton text={f.draft} />
              <Button size="sm" icon={<IconDoc size={15} />} onClick={() => downloadText(`forwarded-${f.txn_id}.txt`, f.draft)}>Download .txt</Button>
            </div>
          </div>
          <pre className="draft">{f.draft}</pre>
        </div>
      ))}
    </div>
  );
}

function ConservationTab({ d }: { d: CD }) {
  return (
    <motion.div className="grid g3" variants={staggerParent} initial="hidden" animate="show">
      {d.conservation.map((c) => (
        <Card key={c.convention} title={<><i style={{ width: 12, height: 12, borderRadius: 3, background: CONV_COLOR[c.convention], display: 'inline-block' }} />{c.convention === 'PR' ? 'Pro-rata' : c.convention === 'LIFO' ? 'LIFO (bounding)' : 'FIFO'}</>}
          right={<motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', delay: 0.3 }} className="check-icon" style={{ background: c.passed ? C.olive : C.terracotta }}>{c.passed ? <IconCheck size={14} /> : <IconAlert size={14} />}</motion.span>}>
          <div className="stack num small" style={{ gap: 4 }}>
            <Eq k="retained" v={c.retained} />
            <Eq k="+ exited" v={c.exited} />
            <Eq k="+ dust" v={c.dust} />
            <Eq k="+ absorbed" v={c.absorbed} />
            <div style={{ borderTop: `1.5px solid ${C.clay}`, margin: '4px 0' }} />
            <Eq k="= loss" v={c.loss} bold />
            <div className="tiny" style={{ color: c.passed ? C.olive : C.terracotta, marginTop: 4 }}>
              difference {rupees(c.difference)} · {c.passed ? 'balanced' : 'does not balance'}
            </div>
          </div>
        </Card>
      ))}
    </motion.div>
  );
}
const Eq = ({ k, v, bold }: { k: string; v: number; bold?: boolean }) => (
  <div className="row between" style={{ fontWeight: bold ? 700 : 450 }}><span className="muted" style={{ fontFamily: 'var(--f-ui)' }}>{k}</span><span>{rupees(v)}</span></div>
);

function AssumptionsTab({ d }: { d: CD }) {
  const items = useMemo(() => d.assumptions, [d]);
  return (
    <ol className="stack" style={{ gap: 8, paddingLeft: 22, margin: 0 }}>
      {items.map((a, i) => (
        <motion.li key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0, transition: { delay: i * 0.05 } }} className="serif" style={{ fontSize: 15 }}>{a}</motion.li>
      ))}
    </ol>
  );
}


function HowTab({ caseId, sel, d }: { caseId: number; sel: string | null; d: CD }) {
  const node = d.nodes.find((n) => n.account_id === sel);
  const ok = !!node && !node.is_victim && node.observable && (node as { kind?: string }).kind !== 'SINK';
  const { data, error, loading } = useAsync(() => (ok && sel ? api.caseExplain(caseId, sel) : Promise.resolve(null)), [caseId, sel, ok]);
  if (!ok) return <p className="muted">Select an account in the list above (not the victim, cash or another bank) to see how its figure was calculated.</p>;
  if (error) return <ErrorCard error={error} />;
  if (loading || !data) return <RowsSkeleton rows={4} />;
  return (
    <div>
      {data.summary && <p className="small" style={{ marginBottom: 12 }}><b>Account {sel}.</b> {data.summary}</p>}
      {data.steps.length === 0 ? <p className="muted">No disputed money reached this account before the reference time.</p>
        : <CalcTimeline steps={data.steps} account={sel ?? ''} />}
    </div>
  );
}


function BasisTab({ caseId }: { caseId: number }) {
  const { data, error, loading } = useAsync(() => api.caseBasis(caseId), [caseId]);
  if (error) return <ErrorCard error={error} />;
  if (loading || !data) return <RowsSkeleton rows={5} />;
  const f = data.facts;
  return (
    <BasisPanel where="cases" rules={data.rules} steps={data.steps} query={data.page_query} queryTitle="Query this page uses to read the result"
      facts={[
        { label: 'transactions in Exasol, all analysed in one run', value: f.transactions_total.toLocaleString('en-IN') },
        { label: `postings on the ${f.accounts} accounts of this case, used to rebuild their balances`, value: f.postings.toLocaleString('en-IN') },
        { label: 'transfers in this money trail', value: String(f.transfers) },
        { label: 'layers (hops away from the victim)', value: String(f.layers ?? 0) },
        ...(data.run ? [{ label: `analysis run #${data.run.run_id} · checksum ${data.run.checksum.slice(7, 19)}`, value: `${Math.round(data.run.duration_s)} s` }] : []),
      ]} />
  );
}
