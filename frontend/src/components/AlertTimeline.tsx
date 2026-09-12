"use client";

import { motion } from "framer-motion";

import { windowLabel } from "@/lib/format";
import type { Alert, AlertType } from "@/lib/types";
import { EmptyState } from "./Skeleton";
import { SEVERITY_STYLES, SeverityTag } from "./StatusPill";

const TYPE_LABEL: Record<AlertType, string> = {
  over_generation: "Over-generation",
  under_generation: "Under-generation",
  ramp_up: "Upward ramp",
  ramp_down: "Downward ramp",
};

export function AlertTimeline({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) {
    return (
      <EmptyState
        title="Clear horizon"
        body="No over-generation, under-generation or ramp events flagged in the forecast window."
      />
    );
  }

  // Chronological here, not by severity: this panel answers "what happens next",
  // while the recommendation panel answers "what should I do first".
  const ordered = [...alerts].sort((a, b) => a.start.localeCompare(b.start));

  return (
    <ol className="relative space-y-3 pl-5">
      <span className="absolute left-[5px] top-2 h-[calc(100%-1rem)] w-px bg-gradient-to-b from-white/20 via-white/10 to-transparent" />
      {ordered.map((alert, index) => {
        const style = SEVERITY_STYLES[alert.severity];
        return (
          <motion.li
            key={alert.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: Math.min(index * 0.04, 0.3) }}
            className="relative"
          >
            <span
              className={`absolute -left-[18px] top-3 h-2.5 w-2.5 rounded-full ring-4 ring-base-900 ${style.bar}`}
            />
            <div className="glass p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`text-xs font-medium ${style.text}`}>
                  {TYPE_LABEL[alert.type]}
                </span>
                <SeverityTag severity={alert.severity} />
                <span className="ml-auto font-mono text-[11px] tabular-nums text-slate-400">
                  {windowLabel(alert.start, alert.end)}
                </span>
              </div>
              <p className="mt-1.5 text-[13px] leading-relaxed text-slate-300">{alert.detail}</p>
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}
