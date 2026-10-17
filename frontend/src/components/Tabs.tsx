import { motion } from 'motion/react';
import { useId } from 'react';

export interface TabDef { key: string; label: string; badge?: string | number }

export function Tabs({ tabs, value, onChange }: { tabs: TabDef[]; value: string; onChange: (k: string) => void }) {
  const id = useId();
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} className={`tab ${value === t.key ? 'active' : ''}`} onClick={() => onChange(t.key)}>
          {t.label}
          {t.badge !== undefined && <span className="badge">{t.badge}</span>}
          {value === t.key && (
            <motion.span className="underline" layoutId={`tab-underline-${id}`} transition={{ type: 'spring', stiffness: 420, damping: 34 }} />
          )}
        </button>
      ))}
    </div>
  );
}
