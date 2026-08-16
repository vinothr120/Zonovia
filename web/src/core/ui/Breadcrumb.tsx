import { Fragment } from "react";

/** Renders an ancestor chain (root-first) as "Building A / Floor 2 / Room 201". Purely
 * presentational — callers compute the chain (e.g. by walking parent_location_id in memory). */
export function Breadcrumb({ segments }: { segments: string[] }) {
  if (segments.length === 0) return <span className="text-slate-400">—</span>;
  return (
    <span className="text-slate-600">
      {segments.map((segment, i) => (
        <Fragment key={i}>
          {i > 0 && <span className="text-slate-300 mx-1">/</span>}
          <span className={i === segments.length - 1 ? "text-slate-900" : undefined}>{segment}</span>
        </Fragment>
      ))}
    </span>
  );
}
