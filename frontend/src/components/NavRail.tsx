import { motion } from 'motion/react';
import { NavLink, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { Button } from './Button';
import {
  IconAsk, IconCases, IconChevron, IconChevronLeft, IconEngine, IconFlask, IconScale,
} from './Icons';

const NAV: { to: string; label: string; icon: ReactNode; match?: (p: string) => boolean }[] = [
  { to: '/analyze', label: 'Live analysis', icon: <IconFlask /> },
  { to: '/cases', label: 'Cases', icon: <IconCases />, match: (p) => p.startsWith('/cases') },
  { to: '/lien-review', label: 'Lien review', icon: <IconScale /> },
  { to: '/ask', label: 'Ask', icon: <IconAsk /> },
  { to: '/system', label: 'System', icon: <IconEngine /> },
];

export function LogoMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <defs>
        <radialGradient id="lg" cx="40%" cy="35%" r="70%">
          <stop offset="0%" stopColor="#FFF7EA" />
          <stop offset="100%" stopColor="#E9D3AE" />
        </radialGradient>
      </defs>
      <circle cx="28" cy="28" r="17" fill="url(#lg)" stroke="#7A2232" strokeWidth="5" />
      <path d="M17 31h22M17 25h22" stroke="#B98B6A" strokeWidth="1.4" />
      <circle cx="28" cy="28" r="5" fill="#E39B2D" />
      <line x1="40" y1="40" x2="54" y2="54" stroke="#2A1B14" strokeWidth="7" strokeLinecap="round" />
    </svg>
  );
}

export function NavRail({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { pathname } = useLocation();
  return (
    <aside className="rail">
      <NavLink to="/" className="brand" title="Back to the TraceHold home page">
        <LogoMark />
        <span className="brand-name">Trace<em>Hold</em></span>
      </NavLink>
      <nav aria-label="Main">
        {NAV.map((n) => {
          const active = n.match ? n.match(pathname) : pathname.startsWith(n.to);
          return (
            <NavLink key={n.to} to={n.to} className={`navlink ${active ? 'active' : ''}`} title={collapsed ? n.label : undefined}>
              {active && (
                <>
                  <motion.span className="nav-bg" layoutId="nav-bg" transition={{ type: 'spring', stiffness: 380, damping: 32 }} />
                  <motion.span className="nav-tick" layoutId="nav-tick" transition={{ type: 'spring', stiffness: 380, damping: 32 }} />
                </>
              )}
              {n.icon}
              <span className="label">{n.label}</span>
            </NavLink>
          );
        })}
      </nav>
      <div className="spacer" />
      <div className="rail-note">
        Decision support only. TraceHold never freezes or releases accounts and never labels anyone. <b>A person decides.</b>
      </div>
      <div className="rail-toggle">
        <Button variant="ghost" size="sm" iconOnly={collapsed} icon={collapsed ? <IconChevron size={16} /> : <IconChevronLeft size={16} />} onClick={onToggle} title={collapsed ? 'Expand navigation' : 'Collapse navigation'}>
          {collapsed ? null : 'Collapse'}
        </Button>
      </div>
    </aside>
  );
}
