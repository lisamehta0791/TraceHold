import { motion } from 'motion/react';
import { Button } from './Button';
import { IconAlert, IconRefresh } from './Icons';

export function ErrorCard({ error, onRetry, title = 'We could not load this page' }: { error: Error; onRetry?: () => void; title?: string }) {
  return (
    <motion.div className="card errcard" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} role="alert">
      <div className="glyph"><IconAlert size={22} /></div>
      <div className="stack">
        <h3>{title}</h3>
        <p className="muted small">{error.message}</p>
        <p className="tiny mute2">
          Tip: check that Exasol is running and the TraceHold server is started (see the README).
        </p>
        {onRetry && (
          <div>
            <Button variant="primary" size="sm" icon={<IconRefresh size={15} />} onClick={onRetry}>Try again</Button>
          </div>
        )}
      </div>
    </motion.div>
  );
}
