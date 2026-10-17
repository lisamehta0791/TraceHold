import { motion, useMotionTemplate, useMotionValue } from 'motion/react';
import { useRef } from 'react';
import type { CSSProperties, MouseEvent, ReactNode } from 'react';
import { riseIn, useMotionOK } from '../lib/motion';

interface CardProps {
  title?: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  onClick?: () => void;
  ruled?: boolean;
  hi?: boolean;
}

/** Paper card: fades up once when it enters the view; a faint warm light follows the pointer on hover. */
export function Card({ title, sub, right, children, className = '', style, onClick, ruled, hi }: CardProps) {
  const motionOK = useMotionOK();
  const ref = useRef<HTMLElement>(null);
  const gx = useMotionValue('50%');
  const gy = useMotionValue('50%');
  const glow = useMotionTemplate`radial-gradient(360px circle at ${gx} ${gy}, rgba(255, 249, 238, 0.4), transparent 60%)`;

  const onMove = (e: MouseEvent) => {
    if (!motionOK || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    gx.set(`${e.clientX - r.left}px`);
    gy.set(`${e.clientY - r.top}px`);
  };

  return (
    <motion.section
      ref={ref}
      variants={riseIn}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.1 }}
      whileHover={onClick && motionOK ? { y: -2 } : undefined}
      transition={{ duration: 0.25 }}
      className={`card ${ruled ? 'ruled' : ''} ${hi ? 'hi' : ''} ${onClick ? 'interactive' : ''} ${className}`}
      style={style}
      onMouseMove={onMove}
      onClick={onClick}
    >
      {motionOK && <motion.div aria-hidden className="card-glow" style={{ background: glow }} />}
      {(title || right) && (
        <div className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {sub && <div className="card-sub">{sub}</div>}
          </div>
          {right}
        </div>
      )}
      {children}
    </motion.section>
  );
}
