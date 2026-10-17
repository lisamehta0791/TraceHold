import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api';
import type { Extraction, PgAccountResult, PgBody, PgResult, PgScenario, SampleLetter } from '../types';
import { LetterReview } from '../components/LetterReview';
import type { ConfirmedFields } from '../components/LetterReview';
import { Button } from '../components/Button';
import { ClassChip, ReqChip, StatusChip } from '../components/Chip';
import { BasisPanel } from '../components/BasisPanel';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { ErrorCard } from '../components/ErrorCard';
import { IconAlert, IconCheck, IconConflict, IconCopy, IconLetter, IconPlay, IconPlus, IconSpark, IconTrash, IconX } from '../components/Icons';
import { CalcTimeline } from '../components/CalcTimeline';
import { PageHead } from '../components/Page';
import { RangeBar } from '../components/RangeBar';
import { C, pct, rupees } from '../lib/format';
import { ease } from '../lib/motion';

const BLANK: PgBody = {
  accounts: [{ name: 'A', opening: 5000 }, { name: 'B', opening: 200000 }],
  transfers: [{ from: 'VICTIM', to: 'A', amount: 50000, minute: 0 }, { from: 'A', to: 'B', amount: 45000, minute: 10 }],
  request: {
    officer: '', designation: '', agency: '', contact: '', reference: '', legal_provision: '',
    action_type: 'TOTAL_FREEZE', stated_amount: 50000,
    targets: [{ account: 'A', scope: 'WHOLE_BALANCE' }, { account: 'B', scope: 'WHOLE_BALANCE' }],
  },
};

const STAGES = ['Loading your case into Exasol', 'Checking the request', 'Rebuilding the money trail', 'Sizing every account', 'Comparing with the request'];

export default function Analyze() {
  const [mode, setMode] = useState<'demo' | 'own' | 'letter'>('demo');
  const [scenarios, setScenarios] = useState<PgScenario[]>([]);
  const [picked, setPicked] = useState<string>('worked');
  const [body, setBody] = useState<PgBody>(BLANK);
  const [result, setResult] = useState<PgResult | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [running, setRunning] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);

  const [params] = useSearchParams();
  useEffect(() => {
    api.scenarios().then((r) => {
      setScenarios(r.scenarios);
      if (params.get('mode') === 'own') { setMode('own'); setBody(structuredClone(BLANK)); return; }
      if (params.get('mode') === 'letter') setMode('letter');
      const want = params.get('scenario');
      const w = r.scenarios.find((s) => s.id === want) ?? r.scenarios.find((s) => s.id === 'worked') ?? r.scenarios[0];
      if (w) { setPicked(w.id); setBody(strip(w)); }
    }).catch((e) => setError(e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pick = (s: PgScenario) => { setPicked(s.id); setBody(strip(s)); setResult(null); };
  const switchMode = (m: 'demo' | 'own' | 'letter') => {
    setMode(m);
    setResult(null);
    if (m === 'own') setBody(structuredClone(BLANK));
    else { const s = scenarios.find((x) => x.id === picked); if (s) setBody(strip(s)); }
  };

  const run = async () => {
    setRunning(true); setError(null);
    try {
      const r = await api.runPlayground(body);
      setResult(r);
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120);
    } catch (e) { setError(e as Error); setResult(null); }
    finally { setRunning(false); }
  };

  return (
    <div>
      <PageHead eyebrow="Live analysis · computed in Exasol" title="Test a case live"
        lede="Build a small fraud case — or pick a demo — and see, step by step, how much of each account the records support holding." />

      {/* ---------------------------------------------------------- 1. data */}
      <section className="an-block">
        <StepTitle n={1} title="Choose your data" />
        <div className="seg">
          {(['demo', 'own', 'letter'] as const).map((m) => (
            <button key={m} className={mode === m ? 'on' : ''} onClick={() => switchMode(m)}>
              {mode === m && <motion.span layoutId="seg-mode" className="seg-on" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
              <span>{m === 'demo' ? 'Use a demo scenario' : m === 'own' ? 'Enter my own values' : 'Read a police letter (AI)'}</span>
            </button>
          ))}
        </div>
        <AnimatePresence mode="wait" initial={false}>
          {mode === 'demo' ? (
            <motion.div key="demo" className="sc-grid" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
              {scenarios.map((s) => (
                <button key={s.id} className={`sc-card ${picked === s.id ? 'on' : ''}`} onClick={() => pick(s)}>
                  {picked === s.id && <motion.span layoutId="sc-on" className="sc-ring" transition={{ type: 'spring', stiffness: 380, damping: 32 }} />}
                  <b>{s.title}</b>
                  <span>{s.summary}</span>
                  <em>Shows: {s.teaches}</em>
                </button>
              ))}
            </motion.div>
          ) : mode === 'letter' ? (
            <motion.div key="letter" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
              <LetterMode scenarios={scenarios} picked={picked} body={body} onPick={pick} onApply={(b) => setBody(b)} />
            </motion.div>
          ) : (
            <motion.p key="own" className="muted small" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              Start from the small example below and change it however you like. Account names are letters/digits (e.g. A, SHOP, MULE2).
            </motion.p>
          )}
        </AnimatePresence>
      </section>

      {/* ---------------------------------------------------------- 2. editor */}
      <section className="an-block">
        <StepTitle n={2} title={mode === 'demo' ? 'The case (you can change any value)' : 'Describe the case'} />
        <Editor body={body} onChange={(b) => { setBody(b); }} />
        <div className="row wrap" style={{ gap: 12, marginTop: 18, alignItems: 'center' }}>
          <Button variant="primary" size="lg" icon={<IconPlay size={16} />} loading={running} onClick={run}>
            {running ? 'Running in Exasol…' : 'Run analysis in Exasol'}
          </Button>
          <span className="tiny muted">Usually 5–15 seconds on a laptop. Everything is calculated inside the Exasol database.</span>
        </div>
        <AnimatePresence>{running && <Progress />}</AnimatePresence>
        {error && <div style={{ marginTop: 14 }}><ErrorCard error={error} title="The analysis could not run" /></div>}
      </section>

      {/* ---------------------------------------------------------- results */}
      <div ref={resultsRef} style={{ scrollMarginTop: 80 }}>
        <AnimatePresence mode="wait">
          {result && !running && <Results key={JSON.stringify(result.totals) + result.engine.total_ms} r={result} />}
        </AnimatePresence>
      </div>
    </div>
  );
}

function strip(s: PgScenario): PgBody {
  return structuredClone({ accounts: s.accounts, transfers: s.transfers, request: s.request });
}

function StepTitle({ n, title, sub }: { n: number | string; title: string; sub?: string }) {
  return (
    <div className="step-title">
      <span className="step-n">{n}</span>
      <div><h2>{title}</h2>{sub && <p className="muted small">{sub}</p>}</div>
    </div>
  );
}

function Progress() {
  const [i, setI] = useState(0);
  useEffect(() => { const t = setInterval(() => setI((x) => Math.min(x + 1, STAGES.length - 1)), 750); return () => clearInterval(t); }, []);
  return (
    <motion.ol className="an-progress" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
      {STAGES.map((s, k) => (
        <li key={s} className={k < i ? 'done' : k === i ? 'now' : ''}>
          <span className="dot">{k < i ? <IconCheck size={11} /> : null}</span>{s}
        </li>
      ))}
    </motion.ol>
  );
}

// ================================================================ letter (CF9)
function LetterMode({ scenarios, picked, body, onPick, onApply }: {
  scenarios: PgScenario[]; picked: string; body: PgBody; onPick: (s: PgScenario) => void; onApply: (b: PgBody) => void;
}) {
  const [letters, setLetters] = useState<SampleLetter[]>([]);
  const [text, setText] = useState('');
  const [ex, setEx] = useState<Extraction | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const [applied, setApplied] = useState<string | null>(null);
  useEffect(() => {
    setEx(null); setApplied(null);
    api.sampleLetters(picked).then((r) => { setLetters(r.letters); setText(r.letters[1]?.text ?? r.letters[0]?.text ?? ''); }).catch(setErr);
  }, [picked]);

  const read = async () => {
    setBusy(true); setErr(null); setEx(null); setApplied(null);
    try {
      setEx(await api.extract(text, { accounts: body.accounts.map((a) => a.name.toUpperCase()), transfers: body.transfers }));
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };

  const apply = async (f: ConfirmedFields, by: string) => {
    if (!ex) return;
    await api.confirmExtraction(ex.extraction_id, f, by);
    const names = new Set(body.accounts.map((a) => a.name.toUpperCase()));
    const accs = ((f.targets as string[]) ?? []).map((a) => a.replace(/^A\/C\s*/i, '').toUpperCase());
    const known = accs.filter((a) => names.has(a));
    const unknown = accs.filter((a) => !names.has(a));
    const action = (f.action_type as string) || '';
    const amount = typeof f.stated_amount === 'number' ? f.stated_amount : null;
    onApply({
      ...body,
      request: {
        officer: (f.officer as string) ?? '', designation: (f.designation as string) ?? '', agency: (f.agency as string) ?? '',
        contact: (f.contact as string) ?? '', reference: (f.case_reference as string) ?? '',
        legal_provision: (f.legal_provision as string) ?? '', action_type: action || 'TOTAL_FREEZE', stated_amount: amount,
        targets: known.map((a) => action === 'LIEN_AMOUNT'
          ? { account: a, scope: 'AMOUNT' as const, amount: amount ?? 0 }
          : { account: a, scope: 'WHOLE_BALANCE' as const }),
      },
    });
    const parts = ['Confirmed fields were placed in the police request below'];
    if (unknown.length) parts.push(`accounts not in this case were left out: ${unknown.join(', ')}`);
    if (!action) parts.push('no action was stated, so "freeze" was assumed');
    setApplied(parts.join('; ') + '. Press "Run analysis in Exasol": the request check will flag anything still missing.');
  };

  return (
    <div className="letter-mode">
      <p className="muted small" style={{ margin: '14px 0 10px' }}>
        Police requests often arrive as free text. The AI reads the checklist fields and quotes where each came from; fixed rules
        then check every value, and you confirm them before anything is analysed. The AI never calculates a figure.
      </p>
      <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
        <span className="tiny muted">Case:</span>
        {scenarios.map((s) => <button key={s.id} className={`chip-btn ${picked === s.id ? 'on' : ''}`} onClick={() => onPick(s)}>{s.title}</button>)}
      </div>
      <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
        <span className="tiny muted">Sample letters:</span>
        {letters.map((l) => (
          <button key={l.id} className={`chip-btn ${text === l.text ? 'on' : ''}`} onClick={() => { setText(l.text); setEx(null); setApplied(null); }}>
            <IconLetter size={13} /> {l.title}
          </button>
        ))}
      </div>
      <textarea className="letter-input" value={text} onChange={(e) => { setText(e.target.value); setEx(null); }} rows={9}
        placeholder="Paste a police letter or message here" />
      <div className="row wrap" style={{ gap: 12, marginTop: 10, alignItems: 'center' }}>
        <Button variant="primary" icon={<IconSpark size={15} />} loading={busy} onClick={read} disabled={text.trim().length < 20}>
          {busy ? 'Reading…' : 'Read the letter with AI'}
        </Button>
        <span className="tiny muted">Only synthetic letters are sent to the model. Usually 3–10 seconds.</span>
      </div>
      {err && <div style={{ marginTop: 12 }}><ErrorCard error={err} title="The letter could not be read" /></div>}
      {ex && <div style={{ marginTop: 16 }}><LetterReview key={ex.extraction_id} ex={ex} onConfirm={apply} confirmLabel="Confirm and use in the request" /></div>}
      {applied && <div className="note olive" style={{ marginTop: 12 }}><IconCheck size={15} /><span>{applied}</span></div>}
    </div>
  );
}

// ================================================================ editor
function Editor({ body, onChange }: { body: PgBody; onChange: (b: PgBody) => void }) {
  const names = body.accounts.map((a) => a.name.trim().toUpperCase()).filter(Boolean);
  const set = (patch: Partial<PgBody>) => onChange({ ...body, ...patch });
  const setReq = (patch: Partial<PgBody['request']>) => set({ request: { ...body.request, ...patch } });
  const target = (a: string) => body.request.targets.find((t) => t.account === a);
  const setTarget = (a: string, t: PgBody['request']['targets'][number] | null) => {
    const rest = body.request.targets.filter((x) => x.account !== a);
    setReq({ targets: t ? [...rest, t] : rest });
  };
  const nextName = () => { for (const c of 'ABCDEFGHIJKLMNOPQRSTUVWXYZ') if (!names.includes(c)) return c; return `X${names.length}`; };

  return (
    <div className="ed-grid">
      <div className="ed-card">
        <h3>Accounts <span className="tiny muted">and the money each already held</span></h3>
        <table className="ed-table">
          <thead><tr><th>Name</th><th>Starting balance (₹)</th><th /></tr></thead>
          <tbody>
            {body.accounts.map((a, i) => (
              <tr key={i}>
                <td><input value={a.name} maxLength={12} onChange={(e) => set({ accounts: body.accounts.map((x, k) => k === i ? { ...x, name: e.target.value.toUpperCase() } : x) })} /></td>
                <td><input type="number" min={0} value={a.opening} onChange={(e) => set({ accounts: body.accounts.map((x, k) => k === i ? { ...x, opening: Number(e.target.value) } : x) })} /></td>
                <td><button className="icon-btn" title="Remove" disabled={body.accounts.length <= 1} onClick={() => set({ accounts: body.accounts.filter((_, k) => k !== i) })}><IconTrash size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <Button size="sm" icon={<IconPlus size={14} />} onClick={() => set({ accounts: [...body.accounts, { name: nextName(), opening: 0 }] })}>Add account</Button>
      </div>

      <div className="ed-card">
        <h3>Transfers <span className="tiny muted">minutes after 14:00</span></h3>
        <table className="ed-table">
          <thead><tr><th>From</th><th>To</th><th>Amount (₹)</th><th>Minute</th><th /></tr></thead>
          <tbody>
            {body.transfers.map((t, i) => (
              <tr key={i}>
                <td><select value={t.from} onChange={(e) => set({ transfers: body.transfers.map((x, k) => k === i ? { ...x, from: e.target.value } : x) })}>
                  <option value="VICTIM">Victim</option>{names.map((n) => <option key={n} value={n}>{n}</option>)}
                </select></td>
                <td><select value={t.to} onChange={(e) => set({ transfers: body.transfers.map((x, k) => k === i ? { ...x, to: e.target.value } : x) })}>
                  {names.map((n) => <option key={n} value={n}>{n}</option>)}
                  <option value="CASH">Cash withdrawal</option><option value="OTHER_BANK">Another bank</option>
                </select></td>
                <td><input type="number" min={1} value={t.amount} onChange={(e) => set({ transfers: body.transfers.map((x, k) => k === i ? { ...x, amount: Number(e.target.value) } : x) })} /></td>
                <td><input type="number" min={0} className="narrow" value={t.minute} onChange={(e) => set({ transfers: body.transfers.map((x, k) => k === i ? { ...x, minute: Number(e.target.value) } : x) })} /></td>
                <td><button className="icon-btn" title="Remove" disabled={body.transfers.length <= 1} onClick={() => set({ transfers: body.transfers.filter((_, k) => k !== i) })}><IconTrash size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <Button size="sm" icon={<IconPlus size={14} />} onClick={() => {
          const last = body.transfers[body.transfers.length - 1];
          set({ transfers: [...body.transfers, { from: names[0] ?? 'VICTIM', to: names[1] ?? names[0] ?? 'CASH', amount: 10000, minute: (last?.minute ?? 0) + 5 }] });
        }}>Add transfer</Button>
      </div>

      <div className="ed-card ed-wide">
        <h3>The police request <span className="tiny muted">leave a field empty to see how a missing detail is caught</span></h3>
        <div className="ed-form">
          {([['officer', 'Issuing officer'], ['designation', 'Designation'], ['agency', 'Police station'], ['contact', 'Contact'],
            ['reference', 'Complaint / FIR reference'], ['legal_provision', 'Legal provision']] as const).map(([k, l]) => (
            <label key={k}><span>{l}</span><input value={body.request[k] ?? ''} onChange={(e) => setReq({ [k]: e.target.value } as Partial<PgBody['request']>)} /></label>
          ))}
          <label><span>Action asked for</span>
            <select value={body.request.action_type} onChange={(e) => setReq({ action_type: e.target.value })}>
              <option value="TOTAL_FREEZE">Freeze the whole account</option>
              <option value="DEBIT_FREEZE">Block debits</option>
              <option value="LIEN_AMOUNT">Hold a stated amount</option>
            </select></label>
          <label><span>Disputed amount stated (₹)</span>
            <input type="number" value={body.request.stated_amount ?? ''} onChange={(e) => setReq({ stated_amount: e.target.value === '' ? null : Number(e.target.value) })} /></label>
        </div>
        <div className="ed-targets">
          <span className="tiny muted">Accounts the police want held:</span>
          {names.map((n) => {
            const t = target(n);
            return (
              <div key={n} className={`ed-target ${t ? 'on' : ''}`}>
                <label className="row" style={{ gap: 6 }}>
                  <input type="checkbox" checked={!!t} onChange={(e) => setTarget(n, e.target.checked ? { account: n, scope: 'WHOLE_BALANCE' } : null)} />
                  <b>{n}</b>
                </label>
                {t && (
                  <>
                    <select value={t.scope} onChange={(e) => setTarget(n, { ...t, scope: e.target.value as 'WHOLE_BALANCE' | 'AMOUNT' })}>
                      <option value="WHOLE_BALANCE">whole balance</option><option value="AMOUNT">an amount</option>
                    </select>
                    {t.scope === 'AMOUNT' && <input type="number" className="narrow" value={t.amount ?? 0} onChange={(e) => setTarget(n, { ...t, amount: Number(e.target.value) })} />}
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ================================================================ results
function Results({ r }: { r: PgResult }) {
  const [acc, setAcc] = useState<string>(r.accounts.find((a) => a.received)?.account_id ?? r.accounts[0]?.account_id);
  const consOK = r.conservation.every((c) => c.passed);
  const account = r.accounts.find((a) => a.account_id === acc);
  const block = (d: number) => ({ initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, ease, delay: d } });
  const sized = r.review.filter((v) => v.upper != null);
  const asked = r.totals.requested;
  const supLo = sized.reduce((s, v) => s + Math.min(v.requested ?? 0, v.lower ?? 0), 0);
  const supHi = sized.reduce((s, v) => s + Math.min(v.requested ?? 0, v.upper ?? 0), 0);
  const unsupported = sized.reduce((s, v) => s + Math.max(0, (v.requested ?? 0) - (v.upper ?? 0)), 0);
  const traced = [Math.min(r.totals.traced_pr, r.totals.traced_fifo), Math.max(r.totals.traced_pr, r.totals.traced_fifo)];
  const headline = r.review.length === 0
    ? `${rupees(r.loss)} was stolen. The records trace ${rupees(traced[0])} – ${rupees(traced[1])} of it to these accounts. No hold was requested.`
    : unsupported > 1
      ? `The police asked to hold ${rupees(asked)}. The records support at most ${rupees(supHi)}, so ${rupees(unsupported)} of the account holders' own money would be held without support.`
      : `The police asked to hold ${rupees(asked)}, and the records support it.`;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <motion.div className="an-summary" {...block(0)}>
        <div style={{ flex: 1 }}>
          <span className="eyebrow">Result</span>
          <h2>{headline}</h2>
          {r.review.length > 0 && (
            <div className="verdict">
              <div><span>Police asked to hold</span><b>{rupees(asked)}</b></div>
              <div><span>Supported by the transaction records</span><b>{supLo === supHi ? rupees(supHi) : `${rupees(supLo)} – ${rupees(supHi)}`}</b></div>
              <div className={unsupported > 1 ? 'warn' : ''}><span>Held without support</span><b>{rupees(unsupported)}</b></div>
            </div>
          )}
          <div className="an-summary-figs">
            <span><b>{rupees(r.loss)}</b>stolen</span>
            <span><b>{rupees(traced[0])} – {rupees(traced[1])}</b>still in these accounts</span>
            <span><b>{rupees(Math.max(0, r.loss - traced[1]))}</b>left the accounts (cash, other banks)</span>
          </div>
        </div>
        <div className="an-summary-side">
          <span className={`pill ${consOK ? 'ok' : 'bad'}`}>{consOK ? <IconCheck size={13} /> : <IconAlert size={13} />} Every rupee accounted for</span>
          <span className="tiny muted">Computed in Exasol in {(r.engine.total_ms / 1000).toFixed(1)} s · as of {r.ref_time}</span>
        </div>
      </motion.div>

      {/* step 1: request */}
      <motion.section className="an-block" {...block(0.05)}>
        <StepTitle n="①" title="Is the request complete and consistent?" sub="Each item the police letter should state is checked, and the stated amount and accounts are checked against the transfers." />
        <div className="row" style={{ gap: 10, marginBottom: 12 }}>{r.request_check.status && <ReqChip s={r.request_check.status} />}</div>
        <ul className="checklist">
          {r.request_check.items.map((it, i) => (
            <motion.li key={it.code + i} className={it.kind} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.03 * i }}>
              <span className="ci">{it.kind === 'OK' ? <IconCheck size={12} /> : it.kind === 'MISSING' ? <IconX size={12} /> : <IconConflict size={12} />}</span>
              <b>{it.label}</b><span className="muted">{it.kind === 'OK' ? 'stated' : it.detail}</span>
            </motion.li>
          ))}
        </ul>
        {r.request_check.draft && <Draft title="Clarification letter drafted for the police" text={r.request_check.draft} />}
      </motion.section>

      {/* step 2: trail */}
      <motion.section className="an-block" {...block(0.1)}>
        <StepTitle n="②" title="Where did the money go?" sub="Every transfer the stolen money passed through, in time order, rebuilt from the victim's transfer hop by hop. The last two columns show how much of each transfer was the victim's money under each counting method." />
        <table className="data-table">
          <thead><tr><th>Time</th><th>From → To</th><th className="num">Amount</th><th className="num">Disputed (pro-rata)</th><th className="num">Disputed (FIFO)</th><th>Where it ends</th></tr></thead>
          <tbody>
            {r.edges.map((e) => (
              <tr key={e.txn_id}>
                <td className="mono">{e.time}</td>
                <td>{label(e.from)} → {label(e.to)}</td>
                <td className="num">{rupees(e.amount)}</td>
                <td className="num" style={{ color: C.oxblood }}>{rupees(e.carried_pr)}</td>
                <td className="num" style={{ color: '#B5781F' }}>{rupees(e.carried_fifo)}</td>
                <td className="tiny">{TERMINAL[e.terminal_state] ?? e.terminal_state}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </motion.section>

      {/* step 3: sizing explained */}
      <motion.section className="an-block" {...block(0.15)}>
        <StepTitle n="③" title="How much of each account is the victim's money?" sub="Money is not labelled once it is mixed, so two disclosed counting rules are used. Pro-rata: every payment carries the account's current share of disputed money. FIFO: the oldest money leaves first." />
        <div className="acc-tabs">
          {r.accounts.map((a) => (
            <button key={a.account_id} className={acc === a.account_id ? 'on' : ''} onClick={() => setAcc(a.account_id)}>
              {acc === a.account_id && <motion.span layoutId="acc-on" className="acc-on" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
              <span>{a.account_id}</span>
            </button>
          ))}
        </div>
        <AnimatePresence mode="wait">
          {account && <AccountExplain key={account.account_id} a={account} />}
        </AnimatePresence>
      </motion.section>

      {/* step 4: review */}
      <motion.section className="an-block" {...block(0.2)}>
        <StepTitle n="④" title="Is the requested hold supported?" sub="Each requested hold is compared with the supported range: within evidence, within range (depends on the method), exceeds evidence, or cannot determine." />
        {r.review.length === 0 ? <p className="muted">No accounts were named in the request.</p> : (
          <div className="review-list">
            {r.review.map((v) => (
              <div key={v.account_id} className="review-row">
                <div className="row between wrap" style={{ gap: 8 }}>
                  <b className="serif" style={{ fontSize: 18 }}>Account {v.account_id}</b>
                  <ClassChip c={v.classification} />
                </div>
                {v.upper != null && <RangeBar lower={v.lower ?? 0} upper={v.upper} requested={v.requested ?? undefined} />}
                <ul className="clean small">{v.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>
              </div>
            ))}
          </div>
        )}
        {r.forwarded.length > 0 && r.forwarded.map((d, i) => <Draft key={i} title="Money left for another bank — request drafted for that bank" text={d} />)}
      </motion.section>

      {/* step 5: conservation */}
      <motion.section className="an-block" {...block(0.25)}>
        <StepTitle n="⑤" title="Is every rupee accounted for?" sub="For each method: money still in accounts + money that left (cash, other banks) + tiny untraced amounts + overdraft repayments must equal the reported loss." />
        <div className="cons-grid">
          {r.conservation.map((c) => (
            <div key={c.convention} className="cons-card">
              <b>{c.convention === 'PR' ? 'Pro-rata' : c.convention === 'FIFO' ? 'FIFO' : 'LIFO (bounding case)'}</b>
              <div className="mono small">{rupees(c.retained)} + {rupees(c.exited)} + {rupees(c.dust)} + {rupees(c.absorbed)}</div>
              <div className="mono small">= {rupees(c.retained + c.exited + c.dust + c.absorbed)} {c.passed ? '✓' : '✗'} {rupees(c.loss)}</div>
            </div>
          ))}
        </div>
      </motion.section>

      <motion.section className="an-block" {...block(0.3)}>
        <StepTitle n="⑥" title="What this result is based on" sub="The rules applied and every SQL script that ran inside Exasol for this analysis. Click a step to read its SQL." />
        <ErrorBoundary compact title="The basis of this result could not be shown.">
        <BasisPanel where="playground" rules={r.engine.rules ?? []} steps={r.engine.steps ?? []}
          facts={[
            { label: 'transfers in the money trail', value: String(r.edges.length) },
            { label: 'accounts analysed', value: String(r.accounts.length) },
            { label: 'passes until the trail stopped changing', value: String(r.engine.layer_passes) },
            { label: `seconds inside Exasol (schema ${r.engine.schema})`, value: (r.engine.engine_ms / 1000).toFixed(1) },
          ]} />
        </ErrorBoundary>
      </motion.section>
    </motion.div>
  );
}

function AccountExplain({ a }: { a: PgAccountResult }) {
  return (
    <motion.div className="acc-explain" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }}>
      <div className="acc-head">
        <div>
          <div className="row" style={{ gap: 8 }}><b className="serif" style={{ fontSize: 20 }}>Account {a.account_id}</b>{a.status !== 'NOT_REACHED' && <StatusChip status={a.status} />}</div>
          <p className="small" style={{ marginTop: 6 }}>{a.summary}</p>
        </div>
        <div className="acc-figs">
          <Fig l="Balance now" v={a.balance} />
          <Fig l="Pro-rata" v={a.retained_pr} c={C.oxblood} />
          <Fig l="FIFO" v={a.retained_fifo} c="#B5781F" />
          <Fig l="Traceable share" s={a.share_lo != null ? `${pct(a.share_lo)} – ${pct(a.share_hi ?? 0)}` : '—'} />
        </div>
      </div>
      <CalcTimeline steps={a.steps} opening={a.opening} account={a.account_id} />
      {a.reasons.length > 0 && a.status !== 'DETERMINED' && <p className="tiny muted">{a.reasons.join(' ')}</p>}
    </motion.div>
  );
}

function Fig({ l, v, s, c }: { l: string; v?: number | null; s?: string; c?: string }) {
  return <div className="fig"><span>{l}</span><b style={{ color: c }}>{s ?? (v == null ? '—' : rupees(v))}</b></div>;
}

function Draft({ title, text }: { title: string; text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <details className="draft">
      <summary>{title}</summary>
      <pre>{text}</pre>
      <Button size="sm" icon={<IconCopy size={14} />} onClick={() => { navigator.clipboard?.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
        {copied ? 'Copied' : 'Copy text'}
      </Button>
    </details>
  );
}

const TERMINAL: Record<string, string> = {
  INTERNAL: 'stays in an account here', CASH_OUT: 'withdrawn as cash', OUT_OF_SCOPE: 'left for another bank',
  CHARGES: 'bank charges', RETURNED_TO_VICTIM: 'returned to the victim',
};

function label(a: string) {
  return a === 'VICTIM' ? 'Victim' : a === 'CASH' ? 'Cash' : a === 'OTHER_BANK' ? 'Another bank' : a;
}
