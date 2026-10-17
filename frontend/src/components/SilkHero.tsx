import { useEffect, useRef } from 'react';

/**
 * Landing backdrop: bundles of fine threads that twist into ribbons and drift,
 * with a few points of light travelling along them. Plain canvas 2D; it pauses
 * when off screen and draws a single still frame for reduced motion.
 */

type Bundle = { n: number; colors: [number, number, number][]; alpha: number; y0: number; y1: number; width: number; freq: number; speed: number; phase: number };

const SAFFRON: [number, number, number] = [227, 155, 45];
const TERRA: [number, number, number] = [194, 85, 58];
const OXBLOOD: [number, number, number] = [122, 34, 50];
const OLIVE: [number, number, number] = [110, 123, 58];
const SAND: [number, number, number] = [205, 180, 138];

const BUNDLES: Bundle[] = [
  // a faint, wide ribbon behind for depth
  { n: 54, colors: [SAND, OLIVE, SAND], alpha: 0.2, y0: 1.02, y1: 0.08, width: 0.5, freq: 2.6, speed: 0.2, phase: 2.1 },
  // the main ribbon
  { n: 110, colors: [SAFFRON, TERRA, OXBLOOD], alpha: 0.4, y0: 0.98, y1: 0.16, width: 0.36, freq: 3.3, speed: 0.3, phase: 0 },
];

const mix = (a: number[], b: number[], t: number) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
function colorAt(cs: [number, number, number][], s: number) {
  const x = s * (cs.length - 1);
  const i = Math.min(cs.length - 2, Math.floor(x));
  return mix(cs[i], cs[i + 1], x - i);
}

function threadY(b: Bundle, s: number, u: number, t: number, H: number, k: number) {
  const center = H * (b.y0 + (b.y1 - b.y0) * Math.pow(u, 0.85)) + H * 0.1 * Math.sin(u * 2.6 + t * b.speed + b.phase);
  const env = 0.2 + 0.8 * Math.sin(Math.PI * (0.12 + u * 0.7));
  const twist = Math.cos(u * b.freq - t * b.speed * 1.6 + b.phase + s * 0.9);
  const wobble = 5 * Math.sin(u * 11 + k * 0.41 + t * 0.7) * s;
  return center + s * H * b.width * env * twist + wobble;
}

export function SilkHero({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let W = 0, H = 0, raf = 0, visible = true, t = 6.5;
    let last = performance.now();
    const pointer = { x: 0.5, y: 0.5, tx: 0.5, ty: 0.5 };
    // points of light: which bundle/thread, position along it, speed
    const sparks = Array.from({ length: 16 }, (_, i) => ({ b: 1, k: Math.floor(Math.random() * BUNDLES[1].n), u: Math.random(), v: 0.035 + Math.random() * 0.05, i }));

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = r.width; H = r.height;
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (still) draw();
    };

    const draw = () => {
      if (W < 2 || H < 2) return; // not laid out yet (hidden, or mid-resize)
      ctx.clearRect(0, 0, W, H);
      const step = Math.max(5, W / 260);
      const tt = t + (pointer.x - 0.5) * 0.8;
      for (const b of BUNDLES) {
        for (let k = 0; k < b.n; k++) {
          const s = k / (b.n - 1) - 0.5;
          const [r, g, bl] = colorAt(b.colors, k / (b.n - 1));
          const edge = 1 - Math.abs(s) * 1.3;
          ctx.strokeStyle = `rgba(${r},${g},${bl},${(b.alpha * (0.35 + 0.65 * edge)).toFixed(3)})`;
          ctx.lineWidth = 0.9;
          ctx.beginPath();
          for (let x = -10; x <= W + 10; x += step) {
            const y = threadY(b, s, x / W, tt, H, k) + (pointer.y - 0.5) * 18 * s;
            if (x === -10) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
      }
      for (const p of sparks) {
        const b = BUNDLES[p.b];
        const s = p.k / (b.n - 1) - 0.5;
        const x = p.u * W;
        const y = threadY(b, s, p.u, tt, H, p.k) + (pointer.y - 0.5) * 18 * s;
        if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
        const fade = Math.sin(Math.PI * p.u);
        const g = ctx.createRadialGradient(x, y, 0, x, y, 14);
        g.addColorStop(0, `rgba(255,214,140,${(0.9 * fade).toFixed(3)})`);
        g.addColorStop(0.25, `rgba(227,155,45,${(0.45 * fade).toFixed(3)})`);
        g.addColorStop(1, 'rgba(227,155,45,0)');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(x, y, 14, 0, Math.PI * 2); ctx.fill();
      }
    };

    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      t += dt;
      pointer.x += (pointer.tx - pointer.x) * 0.04;
      pointer.y += (pointer.ty - pointer.y) * 0.04;
      for (const p of sparks) {
        p.u += p.v * dt;
        if (p.u > 1) { p.u = 0; p.k = Math.floor(Math.random() * BUNDLES[1].n); }
      }
      draw();
      if (visible) raf = requestAnimationFrame(frame);
    };

    const onMove = (e: PointerEvent) => { pointer.tx = e.clientX / window.innerWidth; pointer.ty = e.clientY / window.innerHeight; };
    const io = new IntersectionObserver(([e]) => {
      const was = visible;
      visible = e.isIntersecting;
      if (visible && !was && !still) { last = performance.now(); raf = requestAnimationFrame(frame); }
    });

    resize();
    window.addEventListener('resize', resize);
    io.observe(canvas);
    if (still) draw();
    else { window.addEventListener('pointermove', onMove); raf = requestAnimationFrame(frame); }
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onMove);
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden="true" />;
}
