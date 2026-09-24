/** Loading placeholder: a soft pulsing block, used while a Suspense boundary streams in data.
 *  Respects prefers-reduced-motion via Tailwind's motion-safe pulse. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      role="presentation"
      aria-hidden="true"
      className={`animate-pulse rounded-md bg-surface-2 ${className}`}
    />
  );
}

/** A dashboard-tile shaped skeleton, matching the KPI tile layout. */
export function TileSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-bg p-5 shadow-card">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="mt-3 h-8 w-16" />
      <Skeleton className="mt-3 h-3 w-12" />
    </div>
  );
}
