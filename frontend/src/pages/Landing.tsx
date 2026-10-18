import { AnimatePresence, motion, useInView, useMotionValueEvent, useScroll, useTransform } from 'motion/react';
import type { MotionValue } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { ScrollProgress } from '../components/Ambient';
import { Button } from '../components/Button';
import { Counter } from '../components/Counter';
import { IconCheck, IconChevron, IconDb, IconFlask, IconHand, IconScale, IconX } from '../components/Icons';
import { LogoMark } from '../components/NavRail';
import { SilkHero } from '../components/SilkHero';
import { C, rupeesCompact } from '../lib/format';
import { ease, useMotionOK } from '../lib/motion';
import { useAsync } from '../lib/useAsync';


/** Fade-and-rise once when the block scrolls into view. */
function Reveal({ children, delay = 0, y = 24, className, as = 'div' }: {
  children: ReactNode; delay?: number; y?: number; className?: string; as?: 'div' | 'li' | 'section';
}) {
  const M = as === 'li' ? motion.li : as === 'section' ? motion.section : motion.div;
  return (
    <M className={className} initial={{ opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25 }} transition={{ duration: 0.7, ease, delay }}>
      {children}
    </M>
  );
}

function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ================================================================ page
export default function Landing() {
  const nav = useNavigate();
  const ov = useAsync(() => api.overview(), []);
  const ev = useAsync(() => api.evaluation(), []);
  useEffect(() => { document.title = 'TraceHold — trace the money, size a fair hold'; }, []);

  return (
    <div className="lp">
      <ScrollProgress />
      <Header onOpen={() => nav('/analyze')} />
      <Hero onOpen={() => nav('/analyze')} />
      <Figures ov={ov.data} />
      <Problem />
      <HowItWorks />
      <WorkedExample onTry={() => nav('/analyze?scenario=worked')} />
      <Scenarios onPick={(id) => nav(id ? `/analyze?scenario=${id}` : '/analyze?mode=own')} />
      <Different />
      <Principles />
      <ExasolSection ov={ov.data} ev={ev.data} />
      <Closing onOpen={() => nav('/analyze')} onTry={() => nav('/cases')} />
      <footer className="lp-footer">
        <div className="lp-wrap row between wrap" style={{ gap: 12 }}>
          <span className="row" style={{ gap: 8 }}><LogoMark size={22} /> <b className="serif">TraceHold</b></span>
          <span className="tiny muted">ExaThon India 2026 · Track 01: Money, Risk &amp; Regulation · All data is synthetic · MIT licence © 2026 Lisa Mehta</span>
        </div>
      </footer>
    </div>
  );
}

// ================================================================ header
function Header({ onOpen }: { onOpen: () => void }) {
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  useMotionValueEvent(scrollY, 'change', (y) => setScrolled(y > 40));
  return (
    <header className={`lp-header ${scrolled ? 'scrolled' : ''}`}>
      <div className="lp-wrap row between">
        <button className="lp-brand" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
          <LogoMark size={28} /><span>Trace<em>Hold</em></span>
        </button>
        <nav className="lp-links">
          {[['problem', 'The problem'], ['how', 'How it works'], ['different', 'Why it is different'], ['exasol', 'Built on Exasol']].map(([id, label]) => (
            <button key={id} onClick={() => scrollToId(id)}>{label}</button>
          ))}
        </nav>
        <Button variant="primary" size="sm" icon={<IconChevron size={15} />} onClick={onOpen}>Try it live</Button>
      </div>
    </header>
  );
}

// ================================================================ hero
function Hero({ onOpen }: { onOpen: () => void }) {
  const motionOK = useMotionOK();
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] });
  const copyY = useTransform(scrollYProgress, [0, 1], [0, -90]);
  const fade = useTransform(scrollYProgress, [0, 0.6], [1, 0]);
  const line = (d: number) => ({
    initial: { y: '105%' }, animate: { y: '0%' }, transition: { duration: 1, ease, delay: d },
  });
  const item = (d: number) => ({
    initial: { opacity: 0, y: 16 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.8, ease, delay: d },
  });

  return (
    <section className="lp-hero" ref={ref}>
      <motion.div className="lp-silk-wrap" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.6, ease, delay: 0.2 }}>
        <SilkHero className="lp-silk" />
      </motion.div>
      <motion.div className="lp-wrap" style={motionOK ? { y: copyY, opacity: fade } : undefined}>
      <div className="lp-hero-copy">
        <motion.div className="eyebrow" {...item(0.1)}>Built on Exasol · ExaThon India 2026</motion.div>
        <h1 className="lp-title" aria-label="TraceHold">
          <span className="mask"><motion.span {...line(0.15)}>Trace<em>Hold</em></motion.span></span>
        </h1>
        <p className="lp-tagline" aria-label="Trace the stolen money. Hold only what the records support.">
          <span className="mask"><motion.span {...line(0.35)}>Trace the stolen money.</motion.span></span>
          <span className="mask"><motion.span {...line(0.48)}>Hold only what the records <em>support</em>.</motion.span></span>
        </p>
        <motion.p className="lp-lede" {...item(0.75)}>
          When a fraud is reported, banks are asked to freeze the accounts the money reached — often the whole balance of
          people who received a single payment. TraceHold follows the money through every account inside Exasol and works
          out how much of each balance is really the victim's, with the maths shown.
        </motion.p>
        <motion.div className="row wrap" style={{ gap: 12, marginTop: 28 }} {...item(0.9)}>
          <Button variant="primary" size="lg" icon={<IconChevron size={17} />} onClick={onOpen}>Try it live</Button>
          <Button size="lg" onClick={() => scrollToId('how')}>See how it works</Button>
        </motion.div>
      </div>
      </motion.div>
      <motion.button className="lp-scrollcue" onClick={() => scrollToId('figures')}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.6, duration: 0.8 }} aria-label="Scroll down">
        <span>Scroll</span><i />
      </motion.button>
    </section>
  );
}

// ================================================================ scenarios (horizontal scroll)
const SCENARIO_CARDS = [
  { id: 'worked', t: 'The worked example', d: '₹1,00,000 passes through three accounts. Freezing all three locks ₹6,70,000.', k: '6.7× locked' },
  { id: 'split', t: 'Split, merge and cash-out', d: 'Money is split across mules, merged again and withdrawn as cash.', k: '5 accounts' },
  { id: 'shop', t: 'An innocent shopkeeper', d: 'A shop receives one ₹12,000 payment and has ₹3,32,000 frozen.', k: '28× over-hold' },
  { id: 'otherbank', t: 'Money moves to another bank', d: 'Part of the money leaves our records; a request to that bank is drafted.', k: 'forwarded' },
  { id: 'business', t: 'Mixed into a busy business', d: 'Stolen money disappears into an ₹8 lakh balance and is paid on to suppliers.', k: 'diluted' },
];

function Scenarios({ onPick }: { onPick: (id: string) => void }) {
  return (
    <section className="lp-section" id="scenarios">
      <div className="lp-wrap">
        <Reveal>
          <div className="eyebrow">Try it yourself</div>
          <h2 className="lp-h2">Five cases you can run live, or build your own</h2>
          <p className="muted" style={{ maxWidth: 640 }}>Pick one and TraceHold loads it into Exasol, rebuilds the trail and explains every figure. You can change any number.</p>
        </Reveal>
        <div className="lp-sc-grid">
          {SCENARIO_CARDS.map((c, i) => (
            <Reveal key={c.id} delay={0.04 * i}>
              <button className="lp-sc" onClick={() => onPick(c.id)}>
                <span className="lp-sc-no">0{i + 1}</span>
                <b>{c.t}</b>
                <span>{c.d}</span>
                <em>{c.k}</em>
                <span className="lp-sc-go">Run this case →</span>
              </button>
            </Reveal>
          ))}
          <Reveal delay={0.2}>
            <button className="lp-sc own" onClick={() => onPick('')}>
              <span className="lp-sc-no">+</span><b>Enter your own values</b><span>Accounts, transfers and the police request: your numbers.</span>
              <span className="lp-sc-go">Start from scratch →</span>
            </button>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

// ================================================================ live figures
type OverviewData = Awaited<ReturnType<typeof api.overview>>;
type EvalData = Awaited<ReturnType<typeof api.evaluation>>;

function Figures({ ov }: { ov?: OverviewData }) {
  const items: { label: string; value?: number; fmt: (v: number) => string; sub: string; color: string }[] = [
    { label: 'Transactions analysed', value: ov?.counts.transactions, fmt: (v) => Math.round(v).toLocaleString('en-IN'), sub: `${(ov?.counts.cases ?? 0).toLocaleString('en-IN')} fraud cases`, color: C.ink },
    { label: 'Reported as lost', value: ov?.totals.reported_loss, fmt: (v) => rupeesCompact(v), sub: 'by the victims', color: C.oxblood },
    { label: 'Frozen by whole-balance holds', value: ov?.totals.whole_balance_locked, fmt: (v) => rupeesCompact(v), sub: 'if every named account were frozen', color: C.terracotta },
    { label: 'Supported by the records', value: ov?.totals.supported_upper, fmt: (v) => rupeesCompact(v), sub: `at most · at least ${rupeesCompact(ov?.totals.supported_lower)}`, color: C.olive },
  ];
  return (
    <section className="lp-figures" id="figures">
      <div className="lp-wrap">
        <Reveal className="lp-figures-grid">
          {items.map((it, i) => (
            <motion.div key={it.label} className="lp-figure" initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }} transition={{ duration: 0.6, ease, delay: 0.08 * i }}>
              <span className="lp-figure-label"><i style={{ background: it.color }} />{it.label}</span>
              <span className="lp-figure-value" style={{ color: it.color }}>
                {it.value == null ? '—' : <Counter value={it.value} format={it.fmt} duration={1.6} />}
              </span>
              <span className="tiny muted">{it.sub}</span>
            </motion.div>
          ))}
        </Reveal>
        <p className="tiny mute2 center" style={{ marginTop: 14 }}>Live from the current analysis run in Exasol · synthetic data</p>
      </div>
    </section>
  );
}

// ================================================================ problem
function ScrollText({ text }: { text: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 0.85', 'end 0.5'] });
  const words = text.split(' ');
  return (
    <p ref={ref} className="lp-scrolltext">
      {words.map((w, i) => (
        <Word key={i} progress={scrollYProgress} range={[i / words.length, (i + 1) / words.length]}>{w}</Word>
      ))}
    </p>
  );
}
function Word({ children, progress, range }: { children: string; progress: MotionValue<number>; range: [number, number] }) {
  const opacity = useTransform(progress, range, [0.5, 1]);  // 0.5 keeps unrevealed words at 3:1 contrast (WCAG large text)
  return <><motion.span style={{ opacity }}>{children}</motion.span>{' '}</>;
}

function Problem() {
  return (
    <section className="lp-section" id="problem">
      <div className="lp-wrap">
        <Reveal><div className="eyebrow">The problem</div></Reveal>
        <ScrollText text="An officer deciding how much of an account to hold cannot tell how much of the victim's money actually reached it, because the money is split, mixed with other funds and moved on within minutes." />
        <div className="lp-two">
          <Reveal className="lp-card" delay={0}>
            <div className="lp-card-icon" style={{ background: C.oxblood }}><IconHand size={20} color="#FBEFE2" /></div>
            <h3>Too late and too thin for the victim</h3>
            <p>
              Bengaluru police data shows ₹1,261 crore lost to online fraud up to August 2025, with only about
              <b> 4% traced and returned</b>. The money moves faster than the paperwork.
            </p>
            <span className="lp-source">Deccan Herald, city police data</span>
          </Reveal>
          <Reveal className="lp-card" delay={0.12}>
            <div className="lp-card-icon" style={{ background: C.terracotta }}><IconScale size={20} color="#FBEFE2" /></div>
            <h3>Too broad for the innocent recipient</h3>
            <p>
              Hearing <b>105 petitions</b>, the Rajasthan High Court found whole accounts frozen for disputed amounts
              sometimes under ₹100, freezes that outlived a clean chit, and police letters without the amount or the transaction.
            </p>
            <span className="lp-source">Rajasthan High Court, 20 Aug 2026 (as reported)</span>
          </Reveal>
        </div>
        <Reveal className="lp-note">
          Both failures have one root: there is no quick, defensible way to work out how much of the disputed money is in
          each account. The rules already say <i>hold the disputed sum, not the account</i>. TraceHold is the calculator they
          are missing.
        </Reveal>
      </div>
    </section>
  );
}

// ================================================================ how it works
const STEPS = [
  { title: 'Check the request', text: 'Every request is checked against a configurable checklist (officer, reference, legal provision, transaction, amount) and against the records. Missing or conflicting items produce a ready clarification draft.' },
  { title: 'Reconstruct the trail', text: 'Starting from the reported transfers, the trail is rebuilt layer by layer in time order — through splits, merges, loops, reversals, duplicates and clock skew.' },
  { title: 'Size every account', text: 'Running balances are rebuilt and the disputed funds are allocated under two disclosed conventions, pro-rata and first-in-first-out. The result is a range, never a single silent guess.' },
  { title: 'Compare with what was asked', text: 'The requested hold is compared with the supported range: within evidence, within range, exceeds evidence, or cannot determine when records are missing.' },
  { title: 'Hand over the evidence', text: 'An evidence packet cites the transaction records behind every figure, with a neutral explanation for the account holder and drafts for banks outside the records.' },
];

function HowItWorks() {
  const [active, setActive] = useState(0);
  return (
    <section className="lp-section lp-how" id="how">
      <div className="lp-wrap">
        <Reveal>
          <div className="eyebrow">How it works</div>
          <h2 className="lp-h2">From a vague request to a figure you can defend</h2>
        </Reveal>
        <div className="lp-how-grid">
          <div className="lp-how-sticky">
            <FlowDiagram step={active} />
          </div>
          <ol className="lp-steps">
            {STEPS.map((s, i) => <Step key={s.title} i={i} active={active === i} onActive={setActive} {...s} />)}
          </ol>
        </div>
      </div>
    </section>
  );
}

function Step({ i, title, text, active, onActive }: { i: number; title: string; text: string; active: boolean; onActive: (i: number) => void }) {
  const ref = useRef<HTMLLIElement>(null);
  const inView = useInView(ref, { amount: 0.6 });
  useEffect(() => { if (inView) onActive(i); }, [inView, i, onActive]);
  return (
    <li ref={ref} className={`lp-step ${active ? 'active' : ''}`}>
      <motion.span className="lp-step-no" animate={{ backgroundColor: active ? C.oxblood : 'rgba(0,0,0,0)', color: active ? '#FBEFE2' : C.inkSoft }}
        transition={{ duration: 0.3 }}>{i + 1}</motion.span>
      <motion.div animate={{ opacity: active ? 1 : 0.82 }} transition={{ duration: 0.3 }}>
        <h3>{title}</h3>
        <p>{text}</p>
      </motion.div>
    </li>
  );
}

/** The worked example chain, drawn step by step: victim → A → B → C. */
function FlowDiagram({ step }: { step: number }) {
  const nodes = [
    { id: 'V', label: 'Victim', x: 60, bal: 0 },
    { id: 'A', label: 'A', x: 190, bal: 30000, lo: 25000, hi: 30000 },
    { id: 'B', label: 'B', x: 320, bal: 190000, lo: 24152.54, hi: 70000 },
    { id: 'C', label: 'C', x: 450, bal: 450000, lo: 0, hi: 50847.46 },
  ];
  const amounts = ['₹1,00,000', '₹90,000', '₹4,00,000'];
  const y = 150;
  return (
    <div className="lp-diagram">
      <svg viewBox="0 0 510 330" role="img" aria-label="Worked example trail: victim to A to B to C">
        {/* edges */}
        {[0, 1, 2].map((k) => (
          <g key={k}>
            <motion.path d={`M ${nodes[k].x + 24} ${y} L ${nodes[k + 1].x - 24} ${y}`} stroke={C.oxblood} strokeWidth={3}
              strokeLinecap="round" fill="none"
              initial={false} animate={{ pathLength: step >= 1 ? 1 : 0, opacity: step >= 1 ? 1 : 0.2 }}
              transition={{ duration: 0.6, ease, delay: step === 1 ? k * 0.35 : 0 }} />
            <motion.text x={(nodes[k].x + nodes[k + 1].x) / 2} y={y - 18} textAnchor="middle" className="lp-dg-amt"
              initial={false} animate={{ opacity: step >= 1 ? 1 : 0 }} transition={{ delay: step === 1 ? 0.3 + k * 0.35 : 0 }}>
              {amounts[k]}
            </motion.text>
          </g>
        ))}
        {/* travelling coin on the trail step */}
        <AnimatePresence>
          {step === 1 && (
            <motion.circle key="coin" r={6} cy={y} fill={C.saffron}
              initial={{ cx: nodes[0].x, opacity: 0 }} animate={{ cx: nodes[3].x, opacity: [0, 1, 1, 0] }}
              exit={{ opacity: 0 }} transition={{ duration: 1.6, ease: 'easeInOut' }} />
          )}
        </AnimatePresence>
        {/* nodes */}
        {nodes.map((n) => (
          <g key={n.id}>
            <circle cx={n.x} cy={y} r={24} fill={n.id === 'V' ? C.oxblood : '#FAF4EA'} stroke={n.id === 'V' ? C.oxblood : C.clay} strokeWidth={2} />
            <text x={n.x} y={y + (n.id === 'V' ? 4 : 5)} textAnchor="middle" className={n.id === 'V' ? 'lp-dg-victim' : 'lp-dg-node'}
              fill={n.id === 'V' ? '#FBEFE2' : C.ink}>{n.label}</text>
          </g>
        ))}
        {/* supported range bars under A, B, C */}
        {nodes.slice(1).map((n, k) => {
          const w = 92;
          const x0 = n.x - w / 2;
          const sx = (v: number) => x0 + (v / n.bal) * w;   // bar = this account's balance
          return (
            <motion.g key={n.id} initial={false} animate={{ opacity: step >= 2 ? 1 : 0, y: step >= 2 ? 0 : 8 }}
              transition={{ duration: 0.5, ease, delay: step === 2 ? k * 0.15 : 0 }}>
              <rect x={x0} y={y + 44} width={w} height={8} rx={4} fill={C.paper3} />
              <rect x={sx(n.lo ?? 0)} y={y + 44} width={Math.max(3, sx(n.hi ?? 0) - sx(n.lo ?? 0))} height={8} rx={4} fill={C.olive} />
              <text x={n.x} y={y + 70} textAnchor="middle" className="lp-dg-small">
                {rupeesCompact(n.lo ?? 0, 1)} – {rupeesCompact(n.hi ?? 0, 1)}
              </text>
              <text x={n.x} y={y + 86} textAnchor="middle" className="lp-dg-tiny">of {rupeesCompact(n.bal, 1)}</text>
            </motion.g>
          );
        })}
        {/* request vs evidence flag on C */}
        <motion.g initial={false} animate={{ opacity: step >= 3 ? 1 : 0, y: step >= 3 ? 0 : -6 }} transition={{ duration: 0.45, ease }}>
          <rect x={360} y={40} width={146} height={50} rx={10} fill="#FAF4EA" stroke={C.terracotta} strokeWidth={1.5} />
          <text x={433} y={60} textAnchor="middle" className="lp-dg-flag">Exceeds evidence</text>
          <text x={433} y={78} textAnchor="middle" className="lp-dg-tiny">whole balance = 8.85× upper</text>
          <path d={`M 450 90 L 450 ${y - 26}`} stroke={C.terracotta} strokeWidth={1.5} strokeDasharray="3 3" />
        </motion.g>
        {/* check-request chips */}
        <motion.g initial={false} animate={{ opacity: step === 0 ? 1 : 0 }} transition={{ duration: 0.4 }}>
          {[['Officer', true], ['Reference', true], ['Legal provision', false], ['Amount', true]].map(([label, ok], k) => (
            <g key={String(label)} transform={`translate(${20 + k * 122}, 40)`}>
              <rect width={114} height={28} rx={14} fill="#FAF4EA" stroke={ok ? C.olive : C.terracotta} />
              <text x={57} y={18} textAnchor="middle" className="lp-dg-small">{ok ? '✓' : '✗'} {label}</text>
            </g>
          ))}
        </motion.g>
        {/* evidence packet */}
        <motion.g initial={false} animate={{ opacity: step >= 4 ? 1 : 0, scale: step >= 4 ? 1 : 0.95 }} transition={{ duration: 0.45, ease }}
          style={{ transformOrigin: '100px 285px' }}>
          <rect x={20} y={262} width={470} height={48} rx={10} fill={C.oxblood} />
          <text x={255} y={283} textAnchor="middle" className="lp-dg-packet">Evidence packet · every figure cites its transactions</text>
          <text x={255} y={300} textAnchor="middle" className="lp-dg-packet-sub">Retained + exited = reported loss ✓ · checksum sha256:d05e…</text>
        </motion.g>
      </svg>
      <AnimatePresence mode="wait">
        <motion.div key={step} className="lp-diagram-caption" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }}>
          Step {step + 1} of {STEPS.length} · {STEPS[step].title}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

// ================================================================ worked example
function WorkedExample({ onTry }: { onTry: () => void }) {
  const rows = [
    { acc: 'A', bal: 30000, lo: 25000, hi: 30000 },
    { acc: 'B', bal: 190000, lo: 24152.54, hi: 70000 },
    { acc: 'C', bal: 450000, lo: 0, hi: 50847.46 },
  ];
  const max = 450000;
  return (
    <section className="lp-section lp-tinted">
      <div className="lp-wrap lp-we">
        <Reveal className="lp-we-copy">
          <div className="eyebrow">A worked example</div>
          <h2 className="lp-h2">One lakh, three accounts, six lakh frozen</h2>
          <p>
            A victim pays A ₹1,00,000. A forwards ₹90,000 to B, which already holds ₹5,00,000. B pays ₹4,00,000 to C.
            Freezing all three balances locks <b>₹6,70,000</b>. The records support at most <b>₹1,00,000</b> as the disputed money.
          </p>
          <Button icon={<IconFlask size={16} />} onClick={onTry}>Change the numbers and compute it live</Button>
        </Reveal>
        <div className="lp-we-bars">
          {rows.map((r, i) => (
            <Reveal key={r.acc} delay={0.1 * i} className="lp-we-row">
              <div className="row between"><b className="serif">Account {r.acc}</b><span className="mono tiny">balance {rupeesCompact(r.bal)}</span></div>
              <div className="lp-we-track">
                <motion.div className="lp-we-balance" initial={{ width: 0 }} whileInView={{ width: `${(r.bal / max) * 100}%` }}
                  viewport={{ once: true }} transition={{ duration: 0.9, ease, delay: 0.15 + 0.1 * i }} />
                <motion.div className="lp-we-range" style={{ left: `${(r.lo / max) * 100}%` }}
                  initial={{ width: 0 }} whileInView={{ width: `${Math.max(0.6, ((r.hi - r.lo) / max) * 100)}%` }}
                  viewport={{ once: true }} transition={{ duration: 0.7, ease, delay: 0.6 + 0.1 * i }} />
              </div>
              <div className="row between tiny">
                <span className="muted">supported {rupeesCompact(r.lo, 2)} – {rupeesCompact(r.hi, 2)}</span>
                <span style={{ color: C.terracotta }}>whole-balance hold = {(r.bal / r.hi).toFixed(2)}× upper</span>
              </div>
            </Reveal>
          ))}
          <div className="row" style={{ gap: 16 }}>
            <span className="tiny muted row" style={{ gap: 6 }}><i className="lp-key" style={{ background: C.paper3 }} />whole balance</span>
            <span className="tiny muted row" style={{ gap: 6 }}><i className="lp-key" style={{ background: C.olive }} />supported range</span>
          </div>
        </div>
      </div>
    </section>
  );
}

// ================================================================ different
const COMPARE: [string, boolean | 'partial', boolean][] = [
  ['Trace the money trail across accounts', true, true],
  ['Size how much each account still holds', false, true],
  ['Show uncertainty as a range under stated conventions', false, true],
  ['Flag requests broader than the records support', false, true],
  ['Say “cannot determine” when records are incomplete', false, true],
  ['Check the request itself for missing or conflicting details', false, true],
  ['Evidence packet that cites every transaction', 'partial', true],
];

function Different() {
  const mark = (v: boolean | 'partial') => v === true
    ? <span className="lp-yes"><IconCheck size={15} /></span>
    : v === 'partial' ? <span className="lp-part">reports</span> : <span className="lp-no"><IconX size={13} /></span>;
  return (
    <section className="lp-section" id="different">
      <div className="lp-wrap">
        <Reveal>
          <div className="eyebrow">Why it is different</div>
          <h2 className="lp-h2">Trail tools show where money went. TraceHold sizes what can be held.</h2>
        </Reveal>
        <Reveal className="lp-compare" delay={0.1}>
          <div className="lp-compare-head"><span /><span>Typical fund-trail tools</span><span>TraceHold</span></div>
          {COMPARE.map(([label, them, us], i) => (
            <motion.div key={label} className="lp-compare-row" initial={{ opacity: 0, x: -10 }} whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }} transition={{ duration: 0.45, ease, delay: 0.05 * i }}>
              <span>{label}</span><span>{mark(them)}</span><span>{mark(us)}</span>
            </motion.div>
          ))}
        </Reveal>
        <p className="tiny mute2" style={{ marginTop: 10 }}>
          Based on public descriptions of existing products; capabilities inside banks may differ. TraceHold does not claim to be first.
        </p>
      </div>
    </section>
  );
}

// ================================================================ principles
function Principles() {
  const items = [
    { t: 'A person decides', d: 'TraceHold never freezes or releases anything. It informs the officer who does.' },
    { t: 'No labels, no scores', d: 'It does not decide guilt and never calls anyone a mule. It reports facts.' },
    { t: 'Ranges, not verdicts', d: 'When the conventions disagree, both ends are shown. When records are missing, it says so.' },
    { t: 'Source data is read-only', d: 'The analysis cannot change or delete the records it works from; Exasol refuses it.' },
    { t: 'AI never touches a figure', d: 'AI only reads letters and words answers. Every number comes from SQL and is checked.' },
    { t: 'Synthetic data only', d: 'Every account, case and transaction here is generated. No real person’s data is used.' },
  ];
  return (
    <section className="lp-section lp-tinted">
      <div className="lp-wrap">
        <Reveal>
          <div className="eyebrow">What it will never do</div>
          <h2 className="lp-h2">Decision support, built to be careful</h2>
        </Reveal>
        <dl className="lp-rules">
          {items.map((it, i) => (
            <Reveal key={it.t} delay={0.04 * i} className="lp-rule">
              <dt>{it.t}</dt><dd>{it.d}</dd>
            </Reveal>
          ))}
        </dl>
      </div>
    </section>
  );
}

// ================================================================ exasol
function ExasolSection({ ov, ev }: { ov?: OverviewData; ev?: EvalData }) {
  const fifo = ev?.amount?.find((a) => a.convention === 'FIFO');
  const stats = [
    { v: ov ? `${(ov.counts.transactions / 1e6).toFixed(1)}M` : '—', l: 'transactions traced and sized in one run' },
    { v: ov?.run?.duration_s ? `${Math.round(ov.run.duration_s / 60)} min` : '—', l: 'for the complete analysis, all cases at once' },
    { v: ev ? `${ev.conservation.passed.toLocaleString('en-IN')} / ${ev.conservation.checks.toLocaleString('en-IN')}` : '—', l: 'conservation checks passed' },
    { v: fifo?.within_1_paisa != null ? `${(fifo.within_1_paisa * 100).toFixed(1)}%` : '—', l: 'of account figures match an independent ledger to the paisa' },
  ];
  return (
    <section className="lp-section" id="exasol">
      <div className="lp-wrap lp-exasol">
        <Reveal className="lp-exasol-copy">
          <div className="eyebrow">Built on Exasol Personal</div>
          <h2 className="lp-h2">Every calculation runs inside the database</h2>
          <p>
            Trail reconstruction, running balances, the allocation conventions, request checks and the review queue are all
            set-based SQL in Exasol. Running balances become window functions; pro-rata allocation becomes a log-sum over each
            account's payments; FIFO and LIFO become interval arithmetic. The application only orchestrates.
          </p>
          <p className="muted small">
            The SQL engine is validated against a separate, row-by-row implementation of the same rules. Results are
            reproducible: the same snapshot always gives the same checksum.
          </p>
        </Reveal>
        <div className="lp-exasol-stats">
          {stats.map((s, i) => (
            <Reveal key={s.l} delay={0.08 * i} className="lp-stat">
              <IconDb size={16} color={C.saffron} />
              <span className="lp-stat-v">{s.v}</span>
              <span className="lp-stat-l">{s.l}</span>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

// ================================================================ closing
function Closing({ onOpen, onTry }: { onOpen: () => void; onTry: () => void }) {
  return (
    <section className="lp-closing">
      <div className="lp-wrap center">
        <Reveal>
          <h2 className="lp-h2 light">See what the records support</h2>
          <p className="lp-closing-sub">2,400 synthetic cases, sized and explained. Open any one of them.</p>
          <div className="row wrap" style={{ gap: 12, justifyContent: 'center', marginTop: 24 }}>
            <Button variant="accent" size="lg" icon={<IconChevron size={17} />} onClick={onOpen}>Try it live</Button>
            <Button size="lg" icon={<IconFlask size={16} />} onClick={onTry}>Browse the 2,400 cases</Button>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
