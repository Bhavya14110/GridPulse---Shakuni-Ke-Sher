"use client";

import type { SiteForecast } from "@/lib/types";

/**
 * The inputs behind the prediction. Worth its own panel: when an operator asks
 * "why is the afternoon forecast so low", the answer is in this row, and being
 * able to point at 80% cloud cover is what makes the forecast trustworthy
 * rather than oracular.
 */
export function WeatherPanel({ data }: { data: SiteForecast }) {
  const current = data.current.weather;
  const next = data.forecast[0]?.weather;

  const metrics =
    data.site_type === "solar"
      ? [
          { label: "Irradiance", value: current.ghi_wm2.toFixed(0), unit: "W/m²", accent: "text-solar" },
          { label: "Direct", value: current.direct_radiation_wm2.toFixed(0), unit: "W/m²" },
          { label: "Diffuse", value: current.diffuse_radiation_wm2.toFixed(0), unit: "W/m²" },
          { label: "Cloud cover", value: current.cloudcover_pct.toFixed(0), unit: "%" },
          { label: "Ambient", value: current.temperature_c.toFixed(1), unit: "°C" },
          { label: "Wind 10 m", value: current.windspeed_10m_ms.toFixed(1), unit: "m/s" },
        ]
      : [
          { label: "Hub wind (100 m)", value: current.windspeed_100m_ms.toFixed(1), unit: "m/s", accent: "text-wind" },
          { label: "Surface wind (10 m)", value: current.windspeed_10m_ms.toFixed(1), unit: "m/s" },
          {
            label: "Shear ratio",
            value: (current.windspeed_100m_ms / Math.max(current.windspeed_10m_ms, 0.1)).toFixed(2),
            unit: "×",
          },
          { label: "Cloud cover", value: current.cloudcover_pct.toFixed(0), unit: "%" },
          { label: "Ambient", value: current.temperature_c.toFixed(1), unit: "°C" },
          { label: "Irradiance", value: current.ghi_wm2.toFixed(0), unit: "W/m²" },
        ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {metrics.map((metric) => (
        <div key={metric.label} className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-3">
          <div className="label">{metric.label}</div>
          <div className="mt-1 flex items-baseline gap-1">
            <span className={`font-mono text-xl font-semibold tabular-nums ${metric.accent ?? "text-slate-100"}`}>
              {metric.value}
            </span>
            <span className="text-[11px] text-slate-400">{metric.unit}</span>
          </div>
        </div>
      ))}
      {next && (
        <p className="col-span-2 pt-1 text-[11px] leading-relaxed text-slate-500 sm:col-span-3">
          Current conditions from the Open-Meteo analysis for this site. The same variables, forecast
          hour by hour, are what the model converts into the generation curve above.
        </p>
      )}
    </div>
  );
}
