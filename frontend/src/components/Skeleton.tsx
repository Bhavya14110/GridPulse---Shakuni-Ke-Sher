/** Shimmering placeholder. Shape-matched to the real content so the layout
 *  doesn't jump when data lands. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`relative overflow-hidden rounded-xl bg-white/[0.04] ${className}`}
      aria-hidden
    >
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/[0.07] to-transparent" />
    </div>
  );
}

export function KpiSkeleton() {
  return (
    <div className="glass space-y-3 p-4">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-8 w-32" />
      <Skeleton className="h-3 w-36" />
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="glass flex flex-col items-start gap-3 border-danger/25 bg-danger/[0.06] p-6">
      <div className="flex items-center gap-2 text-danger">
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" strokeWidth={2} stroke="currentColor">
          <path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="font-medium">Something went wrong</span>
      </div>
      <p className="max-w-xl text-sm leading-relaxed text-slate-300">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-slate-200 transition-colors hover:bg-white/10"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="glass flex flex-col items-center gap-2 px-6 py-10 text-center">
      <div className="grid h-11 w-11 place-items-center rounded-full bg-ok/10 text-ok ring-1 ring-ok/25">
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" strokeWidth={2} stroke="currentColor">
          <path d="m5 13 4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <p className="font-medium text-slate-200">{title}</p>
      <p className="max-w-sm text-sm leading-relaxed text-slate-400">{body}</p>
    </div>
  );
}
