import { animate, useInView } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { useMotionOK } from '../lib/motion';

const defaultFmt = (v: number) => Math.round(v).toLocaleString('en-IN');

/** Animated number counter; `format` renders the intermediate value. */
export function Counter({ value, format = defaultFmt, duration = 1.3 }: { value: number; format?: (v: number) => string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: '-20px' });
  const motionOK = useMotionOK();
  const [v, setV] = useState(motionOK ? 0 : value);
  const from = useRef(0);
  useEffect(() => {
    if (!inView) return;
    if (!motionOK) { setV(value); return; }
    const ctl = animate(from.current, value, { duration, ease: [0.16, 1, 0.3, 1], onUpdate: (x) => setV(x) });
    from.current = value;
    return () => ctl.stop();
  }, [value, inView, motionOK, duration]);
  return <span ref={ref}>{format(v)}</span>;
}
