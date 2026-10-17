import type { CSSProperties } from 'react';

export function Skeleton({ w = '100%', h = 14, r = 8, style }: { w?: number | string; h?: number | string; r?: number; style?: CSSProperties }) {
  return <div className="skel" style={{ width: w, height: h, borderRadius: r, ...style }} />;
}

/** Generic page skeleton: header + tiles + panels. */
export function PageSkeleton({ tiles = 4, panels = 2 }: { tiles?: number; panels?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading">
      <Skeleton w={280} h={30} style={{ marginBottom: 10 }} />
      <Skeleton w={460} h={14} style={{ marginBottom: 26 }} />
      {tiles > 0 && (
        <div className={`grid g${Math.min(tiles, 4)}`} style={{ marginBottom: 18 }}>
          {Array.from({ length: tiles }).map((_, i) => (
            <div key={i} className="card">
              <Skeleton w="50%" h={12} />
              <Skeleton w="70%" h={28} style={{ marginTop: 10 }} />
              <Skeleton w="40%" h={10} style={{ marginTop: 10 }} />
            </div>
          ))}
        </div>
      )}
      <div className="grid g2">
        {Array.from({ length: panels }).map((_, i) => (
          <div key={i} className="card">
            <Skeleton w="35%" h={16} />
            <Skeleton h={200} style={{ marginTop: 14 }} r={12} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function RowsSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="stack" style={{ gap: 14 }} aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="row" style={{ gap: 14 }}>
          <Skeleton w={150} h={14} />
          <Skeleton w={90} h={14} />
          <Skeleton h={10} style={{ flex: 1 }} />
          <Skeleton w={90} h={14} />
        </div>
      ))}
    </div>
  );
}
