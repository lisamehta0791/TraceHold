import { AnimatePresence, motion } from 'motion/react';
import { useRef, useState } from 'react';
import type { MouseEvent, ReactNode } from 'react';
import { useMotionOK } from '../lib/motion';

interface ButtonProps {
  children?: ReactNode;
  variant?: 'primary' | 'accent' | 'ghost' | 'outline' | 'default';
  size?: 'sm' | 'md' | 'lg';
  icon?: ReactNode;
  iconOnly?: boolean;
  loading?: boolean;
  disabled?: boolean;
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
  title?: string;
  type?: 'button' | 'submit';
  className?: string;
  href?: string;
  target?: string;
}

interface Ripple { id: number; x: number; y: number; d: number }

/** Button with a gentle press, a soft ink ripple on click and a spinner while loading. */
export function Button({
  children, variant = 'default', size = 'md', icon, iconOnly, loading, disabled, onClick, title, type = 'button', className = '', href, target,
}: ButtonProps) {
  const motionOK = useMotionOK();
  const ref = useRef<HTMLElement>(null);
  const [ripples, setRipples] = useState<Ripple[]>([]);

  const splash = (e: MouseEvent) => {
    if (!ref.current || !motionOK) return;
    const r = ref.current.getBoundingClientRect();
    const d = Math.max(r.width, r.height) * 2;
    const id = Date.now() + Math.random();
    setRipples((rs) => [...rs, { id, x: e.clientX - r.left, y: e.clientY - r.top, d }]);
    setTimeout(() => setRipples((rs) => rs.filter((q) => q.id !== id)), 600);
  };

  const live = motionOK && !disabled && !loading;
  const cls = `btn ${variant !== 'default' ? variant : ''} ${size !== 'md' ? size : ''} ${iconOnly ? 'icon' : ''} ${className}`;
  const inner = (
    <>
      <AnimatePresence initial={false} mode="popLayout">
        {loading ? (
          <motion.span key="spin" className="spinner" initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0, opacity: 0 }} />
        ) : icon ? (
          <motion.span key="icon" style={{ display: 'inline-flex' }} initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.6, opacity: 0 }}>
            {icon}
          </motion.span>
        ) : null}
      </AnimatePresence>
      {children && <span style={{ position: 'relative' }}>{children}</span>}
      {ripples.map((r) => (
        <motion.span
          key={r.id}
          className="ripple"
          style={{ left: r.x, top: r.y, width: r.d, height: r.d }}
          initial={{ scale: 0, opacity: 0.22 }}
          animate={{ scale: 1, opacity: 0 }}
          transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        />
      ))}
    </>
  );
  const common = {
    className: cls,
    title,
    whileTap: live ? { scale: 0.97 } : undefined,
    transition: { type: 'spring' as const, stiffness: 500, damping: 30 },
  };
  if (href) {
    return (
      <motion.a ref={ref as React.RefObject<HTMLAnchorElement>} href={href} target={target} rel={target ? 'noreferrer' : undefined} {...common}
        onClick={(e: MouseEvent<HTMLAnchorElement>) => splash(e)}>
        {inner}
      </motion.a>
    );
  }
  return (
    <motion.button
      ref={ref as React.RefObject<HTMLButtonElement>}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...common}
      onClick={(e: MouseEvent<HTMLButtonElement>) => { splash(e); onClick?.(e); }}
    >
      {inner}
    </motion.button>
  );
}
