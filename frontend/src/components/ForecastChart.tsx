"use client";

import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { hourLabel, mw, shortTime } from "@/lib/format";
import type { Alert, SiteForecast } from "@/lib/types";

interface Props {
  data: SiteForecast;
  /** How many hours of the forward horizon to draw. */
  horizon: number;
}

const ACCENT = {
  solar: { line: "#fbbf24", band: "#f59e0b", soft: "rgba(251,191,36,0.16)" },
  wind: { line: "#22d3ee", band: "#06b6d4", soft: "rgba(34,211,238,0.16)" },
};

const WINDOW_FILL: Record<string, string> = {
  over_generation: "rgba(248,113,113,0.16)",
  under_generation: "rgba(96,165,250,0.16)",
};

const WINDOW_STROKE: Record<string, string> = {
  over_generation: "rgba(248,113,113,0.55)",
  under_generation: "rgba(96,165,250,0.55)",
};

interface Row {
  ts: string;
  actual?: number;
  predicted?: number;
  /** Lower edge of the confidence band; the base of the stacked area. */
  lower?: number;
  /** Band height stacked on top of `lower`, so the two together shade p10-p90. */
  bandHeight?: number;
  potential?: number;
  ghi?: number;
  wind?: number;
  cloud?: number;
  temp?: number;
}

export function ForecastChart({ data, horizon }: Props) {
  const accent = ACCENT[data.site_type];
  const forecast = useMemo(() => data.forecast.slice(0, horizon), [data.forecast, horizon]);

  // Past actuals and the forward forecast share one timeline. Seeing where the
  // recorded line hands over to the predicted one is most of the value of an
  // operational chart -- a forecast with no context behind it is just a curve.
  const rows: Row[] = useMemo(() => {
    const history = data.history.slice(-24).map<Row>((point) => ({
      ts: point.timestamp,
      actual: point.actual_kw,
    }));

    const future = forecast.map<Row>((point) => ({
      ts: point.timestamp,
      predicted: point.predicted_kw,
      lower: point.lower_kw,
      bandHeight: Math.max(point.upper_kw - point.lower_kw, 0),
      potential: point.potential_kw,
      ghi: point.weather.ghi_wm2,
      wind: point.weather.windspeed_100m_ms,
      cloud: point.weather.cloudcover_pct,
      temp: point.weather.temperature_c,
    }));

    // Stitch the two together so the actual line doesn't end in mid-air.
    if (history.length && future.length) {
      history[history.length - 1].predicted = future[0].predicted;
    }
    return [...history, ...future];
  }, [data.history, forecast]);

  const horizonEnd = forecast.at(-1)?.timestamp ?? "";
  const visibleAlerts = data.alerts.filter((alert) => alert.start <= horizonEnd);

  const shadedWindows = visibleAlerts.filter(
    (alert) => alert.type === "over_generation" || alert.type === "under_generation",
  );
  const rampMarkers = visibleAlerts.filter(
    (alert) => alert.type === "ramp_up" || alert.type === "ramp_down",
  );

  const nowBoundary = data.history.at(-1)?.timestamp ?? forecast[0]?.timestamp;
  // Alerts carry their trigger level in kW already; only fall back to the 85%
  // default when the horizon happens to contain no over-generation window.
  const overLimitKw =
    thresholdOf(visibleAlerts, "over_generation", 0) || data.export_limit_kw * 0.85;
  const underFloorKw = thresholdOf(visibleAlerts, "under_generation", 0);
  const isConstrained = data.export_limit_kw < data.capacity_kw;

  return (
    <div className="h-[420px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 12, right: 16, bottom: 4, left: 4 }}>
          <defs>
            <linearGradient id={`band-${data.site_id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={accent.band} stopOpacity={0.3} />
              <stop offset="100%" stopColor={accent.band} stopOpacity={0.08} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 6" vertical={false} />

          <XAxis
            dataKey="ts"
            tickFormatter={(value: string) => hourLabel(value)}
            stroke="rgba(148,163,184,0.35)"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            tickLine={false}
            interval={Math.max(Math.floor(rows.length / 12), 1)}
            minTickGap={16}
          />
          <YAxis
            tickFormatter={(value: number) => `${Math.round(value / 1000)}`}
            stroke="rgba(148,163,184,0.35)"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={44}
            label={{
              value: "MW",
              angle: 0,
              position: "top",
              offset: 12,
              fill: "#64748b",
              fontSize: 11,
            }}
          />

          {/* Risk windows sit behind the data so they read as background context. */}
          {shadedWindows.map((alert) => (
            <ReferenceArea
              key={alert.id}
              x1={alert.start}
              x2={alert.end}
              fill={WINDOW_FILL[alert.type]}
              stroke={WINDOW_STROKE[alert.type]}
              strokeOpacity={0.5}
              strokeDasharray="3 3"
              ifOverflow="extendDomain"
            />
          ))}

          {rampMarkers.map((alert) => (
            <ReferenceLine
              key={alert.id}
              x={alert.end}
              stroke={alert.type === "ramp_down" ? "#fb923c" : "#a78bfa"}
              strokeDasharray="2 4"
              strokeWidth={1.5}
            />
          ))}

          {isConstrained && (
            <ReferenceLine
              y={data.export_limit_kw}
              stroke="#f87171"
              strokeDasharray="6 4"
              strokeWidth={1.5}
              label={{
                value: `Export limit ${Math.round(data.export_limit_kw / 1000)} MW`,
                position: "insideTopRight",
                fill: "#fca5a5",
                fontSize: 10,
              }}
            />
          )}
          {overLimitKw > 0 && (
            <ReferenceLine
              y={overLimitKw}
              stroke="rgba(248,113,113,0.5)"
              strokeDasharray="3 5"
              label={{
                value: "over-gen trigger",
                position: "insideBottomRight",
                fill: "#fca5a5",
                fontSize: 10,
              }}
            />
          )}
          {underFloorKw > 0 && (
            <ReferenceLine
              y={underFloorKw}
              stroke="rgba(96,165,250,0.55)"
              strokeDasharray="3 5"
              label={{
                value: "under-gen floor",
                position: "insideTopRight",
                fill: "#93c5fd",
                fontSize: 10,
              }}
            />
          )}

          {nowBoundary && (
            <ReferenceLine
              x={nowBoundary}
              stroke="rgba(226,232,240,0.55)"
              strokeWidth={1.5}
              label={{ value: "NOW", position: "top", fill: "#e2e8f0", fontSize: 10 }}
            />
          )}

          {/* Two stacked areas draw the p10-p90 band: an invisible pedestal at
              the lower edge, then the band height on top of it. */}
          <Area
            type="monotone"
            dataKey="lower"
            stackId="band"
            stroke="none"
            fill="transparent"
            isAnimationActive={false}
            activeDot={false}
          />
          <Area
            type="monotone"
            dataKey="bandHeight"
            stackId="band"
            stroke="none"
            fill={`url(#band-${data.site_id})`}
            isAnimationActive={false}
            activeDot={false}
          />

          <Line
            type="monotone"
            dataKey="potential"
            stroke="rgba(148,163,184,0.45)"
            strokeWidth={1.2}
            strokeDasharray="4 4"
            dot={false}
            isAnimationActive={false}
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
            stroke={accent.line}
            strokeWidth={2.6}
            dot={false}
            animationDuration={800}
          />

          <Tooltip
            content={<ForecastTooltip siteType={data.site_type} capacity={data.capacity_kw} alerts={visibleAlerts} />}
            cursor={{ stroke: "rgba(226,232,240,0.3)", strokeWidth: 1 }}
          />
        </ComposedChart>
      </ResponsiveContainer>

      <ChartLegend accent={accent.line} hasWindows={shadedWindows.length > 0} hasRamps={rampMarkers.length > 0} />
    </div>
  );
}

/** Pull a threshold off whichever alert of that type exists, else a fallback. */
function thresholdOf(alerts: Alert[], type: string, fallback: number): number {
  const match = alerts.find((alert) => alert.type === type);
  return match ? match.threshold_kw : fallback;
}

function ChartLegend({
  accent,
  hasWindows,
  hasRamps,
}: {
  accent: string;
  hasWindows: boolean;
  hasRamps: boolean;
}) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-5 gap-y-1.5 px-2 text-[11px] text-slate-400">
      <Swatch color="#e2e8f0">Recorded output</Swatch>
      <Swatch color={accent}>Forecast</Swatch>
      <Swatch color={accent} faded>
        80% confidence band
      </Swatch>
      <Swatch color="rgba(148,163,184,0.6)" dashed>
        Clear-sky potential
      </Swatch>
      {hasWindows && (
        <>
          <Swatch color="rgba(248,113,113,0.7)" block>
            Over-generation window
          </Swatch>
          <Swatch color="rgba(96,165,250,0.7)" block>
            Under-generation window
          </Swatch>
        </>
      )}
      {hasRamps && (
        <Swatch color="#fb923c" dashed>
          Ramp event
        </Swatch>
      )}
    </div>
  );
}

function Swatch({
  color,
  children,
  dashed,
  faded,
  block,
}: {
  color: string;
  children: React.ReactNode;
  dashed?: boolean;
  faded?: boolean;
  block?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {block ? (
        <span className="h-2.5 w-4 rounded-[3px]" style={{ background: color, opacity: 0.35 }} />
      ) : (
        <span
          className="h-0 w-4 border-t-2"
          style={{
            borderColor: color,
            borderStyle: dashed ? "dashed" : "solid",
            opacity: faded ? 0.4 : 1,
            borderTopWidth: faded ? 8 : 2,
          }}
        />
      )}
      {children}
    </span>
  );
}

function ForecastTooltip({
  active,
  payload,
  label,
  siteType,
  capacity,
  alerts,
}: {
  active?: boolean;
  payload?: { payload: Row }[];
  label?: string;
  siteType: "solar" | "wind";
  capacity: number;
  alerts: Alert[];
}) {
  if (!active || !payload?.length || !label) return null;
  const row = payload[0].payload;
  const isForecast = row.predicted !== undefined && row.actual === undefined;

  // Surface any risk window this hour falls inside, so hovering a shaded region
  // tells you what it is without hunting through the alert list.
  const covering = alerts.filter((alert) => label >= alert.start && label <= alert.end);

  return (
    <div className="min-w-[230px] rounded-xl border border-white/15 bg-base-800/95 p-3 shadow-xl backdrop-blur-xl">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <span className="text-xs font-medium text-slate-200">{shortTime(label)}</span>
        <span className="text-[10px] uppercase tracking-wider text-slate-500">
          {isForecast ? "forecast" : "recorded"}
        </span>
      </div>

      {row.actual !== undefined && (
        <Row label="Recorded" value={mw(row.actual)} color="#e2e8f0" />
      )}
      {row.predicted !== undefined && (
        <Row
          label="Predicted"
          value={mw(row.predicted)}
          color={siteType === "solar" ? "#fbbf24" : "#22d3ee"}
        />
      )}
      {row.lower !== undefined && row.bandHeight !== undefined && (
        <Row
          label="80% range"
          value={`${mw(row.lower)} – ${mw(row.lower + row.bandHeight)}`}
          color="#94a3b8"
        />
      )}
      {row.predicted !== undefined && (
        <Row
          label="Capacity factor"
          value={`${((row.predicted / capacity) * 100).toFixed(0)}%`}
          color="#94a3b8"
        />
      )}

      {(row.ghi !== undefined || row.wind !== undefined) && (
        <div className="mt-2 border-t border-white/10 pt-2 text-[11px] text-slate-400">
          {siteType === "solar" ? (
            <>
              <span>{row.ghi?.toFixed(0)} W/m² irradiance</span>
              <span className="mx-1.5 text-slate-600">·</span>
              <span>{row.cloud?.toFixed(0)}% cloud</span>
              <span className="mx-1.5 text-slate-600">·</span>
              <span>{row.temp?.toFixed(0)}°C</span>
            </>
          ) : (
            <>
              <span>{row.wind?.toFixed(1)} m/s at hub height</span>
              <span className="mx-1.5 text-slate-600">·</span>
              <span>{row.temp?.toFixed(0)}°C</span>
            </>
          )}
        </div>
      )}

      {covering.map((alert) => (
        <div
          key={alert.id}
          className="mt-2 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1.5 text-[11px] leading-snug text-slate-300"
        >
          {alert.headline}
        </div>
      ))}
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-0.5 text-xs">
      <span className="text-slate-400">{label}</span>
      <span className="font-mono tabular-nums" style={{ color }}>
        {value}
      </span>
    </div>
  );
}
