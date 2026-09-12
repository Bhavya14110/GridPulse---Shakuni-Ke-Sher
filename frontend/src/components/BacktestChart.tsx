"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { hourLabel, mw, shortTime } from "@/lib/format";
import type { HistoricalBacktest, SiteType } from "@/lib/types";

/**
 * The credibility panel: what the model said would happen, against what did.
 *
 * The backend builds this by rewinding to each morning and re-running the
 * forecast with only the data available then -- it never sees the answers. So
 * the two lines agreeing is a real result, not the model reading ahead.
 */
export function BacktestChart({
  data,
  siteType,
  compact = false,
}: {
  data: HistoricalBacktest;
  siteType: SiteType;
  compact?: boolean;
}) {
  const accent = siteType === "solar" ? "#fbbf24" : "#22d3ee";
  const rows = data.points.map((point) => ({
    ts: point.timestamp,
    actual: point.actual_kw,
    predicted: point.predicted_kw,
  }));

  if (!rows.length) {
    return (
      <p className="px-1 py-6 text-sm text-slate-400">
        Not enough recorded history yet to score a day-ahead backtest.
      </p>
    );
  }

  return (
    <div className={compact ? "h-[200px] w-full" : "h-[280px] w-full"}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.1)" strokeDasharray="3 6" vertical={false} />
          <XAxis
            dataKey="ts"
            tickFormatter={(value: string) => hourLabel(value)}
            stroke="rgba(148,163,184,0.3)"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            interval={Math.max(Math.floor(rows.length / 8), 1)}
            minTickGap={20}
          />
          <YAxis
            tickFormatter={(value: number) => `${Math.round(value / 1000)}`}
            stroke="rgba(148,163,184,0.3)"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={36}
          />
          <Line
            type="monotone"
            dataKey="actual"
            stroke="#e2e8f0"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="predicted"
            stroke={accent}
            strokeWidth={2}
            strokeDasharray="5 3"
            dot={false}
            animationDuration={700}
          />
          <Tooltip
            cursor={{ stroke: "rgba(226,232,240,0.25)" }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length || !label) return null;
              const actual = payload.find((p) => p.dataKey === "actual")?.value as number;
              const predicted = payload.find((p) => p.dataKey === "predicted")?.value as number;
              const error = actual - predicted;
              return (
                <div className="rounded-xl border border-white/15 bg-base-800/95 p-3 text-xs shadow-xl backdrop-blur-xl">
                  <div className="mb-1.5 text-slate-200">{shortTime(String(label))}</div>
                  <div className="flex justify-between gap-5">
                    <span className="text-slate-400">Actual</span>
                    <span className="font-mono text-slate-100">{mw(actual)}</span>
                  </div>
                  <div className="flex justify-between gap-5">
                    <span className="text-slate-400">Forecast</span>
                    <span className="font-mono" style={{ color: accent }}>
                      {mw(predicted)}
                    </span>
                  </div>
                  <div className="mt-1 flex justify-between gap-5 border-t border-white/10 pt-1">
                    <span className="text-slate-400">Error</span>
                    <span className="font-mono text-slate-300">
                      {error >= 0 ? "+" : ""}
                      {mw(error)}
                    </span>
                  </div>
                </div>
              );
            }}
          />
        </LineChart>
      </ResponsiveContainer>

      <div className="mt-1 flex items-center gap-5 px-1 text-[11px] text-slate-400">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0 w-4 border-t-2 border-slate-200" /> Actual
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0 w-4 border-t-2 border-dashed" style={{ borderColor: accent }} /> Day-ahead
          forecast
        </span>
      </div>
    </div>
  );
}
