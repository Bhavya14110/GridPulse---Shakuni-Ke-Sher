"use client";

import { useEffect, useState } from "react";

/** UTC clock in the header. Grid operations run on UTC, and so does this app. */
export function LiveClock() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    // Set on mount rather than at render: the server and the browser would
    // otherwise disagree by a second and React would flag a hydration mismatch.
    setNow(new Date());
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex items-center gap-2.5">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-ok" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-ok" />
      </span>
      <span className="font-mono text-sm tabular-nums text-slate-300">
        {now ? now.toISOString().slice(11, 19) : "--:--:--"}
        <span className="ml-1 text-[10px] text-slate-500">UTC</span>
      </span>
    </div>
  );
}
