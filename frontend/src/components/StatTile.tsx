import type { ReactNode } from 'react';
import { Card } from './Card';
import { Counter } from './Counter';

interface StatTileProps {
  label: string;
  value: number;
  format?: (v: number) => string;
  sub?: ReactNode;
  swatch?: string;
  accent?: string;
  small?: boolean;
}

export function StatTile({ label, value, format, sub, swatch, accent, small }: StatTileProps) {
  return (
    <Card>
      <div className="stat">
        <span className="label">
          {swatch && <span className="swatch" style={{ background: swatch }} />}
          {label}
        </span>
        <span className="value" style={{ color: accent, fontSize: small ? '1.35rem' : undefined }}>
          <Counter value={value} format={format} />
        </span>
        {sub && <span className="sub">{sub}</span>}
      </div>
    </Card>
  );
}
