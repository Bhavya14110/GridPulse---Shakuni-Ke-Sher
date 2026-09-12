"use client";

import { motion } from "framer-motion";

import { mw, mwh, windowLabel } from "@/lib/format";
import type { ActionType, Recommendation } from "@/lib/types";
import { EmptyState } from "./Skeleton";
import { SEVERITY_STYLES, SeverityTag } from "./StatusPill";

const ACTION_META: Record<ActionType, { label: string; icon: React.ReactNode }> = {
  curtail: { label: "Curtailment", icon: <ScissorsIcon /> },
  storage_charge: { label: "Storage", icon: <BatteryIcon /> },
  backup_activation: { label: "Backup supply", icon: <PlugIcon /> },
  spinning_reserve: { label: "Spinning reserve", icon: <GaugeIcon /> },
  grid_absorption_check: { label: "Grid absorption", icon: <NetworkIcon /> },
};

/**
 * Every card here is built entirely from the API response -- the title, the
 * severity, the window, the quantity (with its unit) and the reason sentence
 * all come back from the recommendation engine. Nothing on this panel is
 * written in the frontend, which is why the wording tracks the forecast when it
 * changes. The unit travels with the number because a ramp action is quoted in
 * MW of reserve while a curtailment is quoted in MWh of energy.
 */
export function RecommendationPanel({
  recommendations,
  limit,
}: {
  recommendations: Recommendation[];
  limit?: number;
}) {
  const visible = limit ? recommendations.slice(0, limit) : recommendations;

  if (!visible.length) {
    return (
      <EmptyState
        title="No action needed"
        body="Forecast output stays inside this site's limits for the whole horizon. Nothing to curtail, dispatch or cover."
      />
    );
  }

  return (
    <div className="space-y-3">
      {visible.map((rec, index) => (
        <RecommendationCard key={rec.id} rec={rec} index={index} />
      ))}
      {limit && recommendations.length > limit && (
        <p className="px-1 pt-1 text-xs text-slate-500">
          + {recommendations.length - limit} more over the rest of the horizon
        </p>
      )}
    </div>
  );
}

function RecommendationCard({ rec, index }: { rec: Recommendation; index: number }) {
  const style = SEVERITY_STYLES[rec.severity];
  const meta = ACTION_META[rec.action];

  return (
    <motion.article
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.06, 0.4), ease: [0.16, 1, 0.3, 1] }}
      className={`glass glass-hover relative overflow-hidden border-l-0 p-4 pl-5`}
    >
      {/* Severity reads as a colour bar first, text second. */}
      <span className={`absolute left-0 top-0 h-full w-1 ${style.bar}`} />

      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${style.text}`}>
          <span className="opacity-90">{meta.icon}</span>
          {meta.label}
        </span>
        <SeverityTag severity={rec.severity} />
        <span className="ml-auto font-mono text-[11px] tabular-nums text-slate-400">
          {windowLabel(rec.window_start, rec.window_end)}
        </span>
      </div>

      <h4 className="mt-2 text-[15px] font-semibold leading-snug text-white">{rec.title}</h4>

      <p className="mt-1.5 text-[13px] leading-relaxed text-slate-300">{rec.reason}</p>

      <div className="mt-3 flex items-center gap-2 border-t border-white/[0.07] pt-2.5">
        <span className="label">{rec.quantity_label}</span>
        <span className="font-mono text-xs tabular-nums text-slate-200">
          {rec.quantity_unit === "kW" ? mw(rec.quantity) : mwh(rec.quantity)}
        </span>
      </div>
    </motion.article>
  );
}

function ScissorsIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8}>
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M20 4 8.12 15.88M14.47 14.48 20 20M8.12 8.12 12 12" strokeLinecap="round" />
    </svg>
  );
}

function BatteryIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8}>
      <rect x="2" y="7" width="16" height="10" rx="2" />
      <path d="M22 11v2" strokeLinecap="round" />
      <path d="m10 9-2 3h3l-2 3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PlugIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8}>
      <path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0V8ZM12 17v5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GaugeIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8}>
      <path d="M3 18a9 9 0 1 1 18 0" strokeLinecap="round" />
      <path d="m12 14 4-4" strokeLinecap="round" />
    </svg>
  );
}

function NetworkIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8}>
      <circle cx="12" cy="5" r="2.5" />
      <circle cx="5" cy="19" r="2.5" />
      <circle cx="19" cy="19" r="2.5" />
      <path d="M12 7.5v4m0 0-5 5m5-5 5 5" strokeLinecap="round" />
    </svg>
  );
}
