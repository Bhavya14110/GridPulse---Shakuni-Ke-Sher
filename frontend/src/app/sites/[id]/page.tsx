"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AlertTimeline } from "@/components/AlertTimeline";
import { BacktestChart } from "@/components/BacktestChart";
import { ForecastChart } from "@/components/ForecastChart";
import { KpiCard } from "@/components/KpiCard";
import { RecommendationPanel } from "@/components/RecommendationPanel";
import { ErrorState, KpiSkeleton, Skeleton } from "@/components/Skeleton";
import { StatusPill } from "@/components/StatusPill";
import { WeatherPanel } from "@/components/WeatherPanel";
import { api } from "@/lib/api";
import { mw, mwh, relativeTime } from "@/lib/format";
import type { HistoricalBacktest, Site, SiteForecast } from "@/lib/types";

const HORIZONS = [24, 48, 72];

export default function SiteDetailPage() {
  const params = useParams<{ id: string }>();
  const siteId = Number(params.id);

  const [forecast, setForecast] = useState<SiteForecast | null>(null);
  const [site, setSite] = useState<Site | null>(null);
  const [backtest, setBacktest] = useState<HistoricalBacktest | null>(null);
  const [horizon, setHorizon] = useState(72);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      // The forecast bundle is the page's critical path, so fetch it first and
      // let the two slower/secondary calls resolve behind it.
      const [forecastData, siteData] = await Promise.all([
        api.forecast(siteId, 72),
        api.site(siteId),
      ]);
      setForecast(forecastData);
      setSite(siteData);

      const history = await api.historical(siteId, 7);
      setBacktest(history);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [siteId]);

  useEffect(() => {
    if (Number.isNaN(siteId)) {
      setError("That site id isn't a number.");
      return;
    }
    void load();
  }, [load, siteId]);

  if (error && !forecast) {
    return (
      <div className="space-y-4 pt-4">
        <BackLink />
        <ErrorState message={error} onRetry={() => void load()} />
      </div>
    );
  }

  const isSolar = forecast?.site_type === "solar";
  const accent = isSolar ? "solar" : "wind";

  return (
    <div className="space-y-5">
      <BackLink />

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <motion.h1
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-2xl font-semibold tracking-tight text-white sm:text-[28px]"
            >
              {forecast?.site_name ?? "Loading…"}
            </motion.h1>
            {forecast && <StatusPill status={forecast.alert_summary.status} />}
            {forecast && (
              <span
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider ${
                  isSolar ? "bg-solar/10 text-solar" : "bg-wind/10 text-wind"
                }`}
              >
                {forecast.site_type}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-slate-400">
            {site?.region}
            {site && (
              <>
                <span className="mx-1.5 text-slate-600">·</span>
                {site.latitude.toFixed(3)}, {site.longitude.toFixed(3)}
              </>
            )}
            {forecast && (
              <>
                <span className="mx-1.5 text-slate-600">·</span>
                Forecast issued {relativeTime(forecast.generated_at)}
              </>
            )}
          </p>
          {site?.notes && (
            <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-slate-500">
              {site.notes}
            </p>
          )}
        </div>

        <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-white/5 p-1">
          {HORIZONS.map((hours) => (
            <button
              key={hours}
              onClick={() => setHorizon(hours)}
              className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
                horizon === hours
                  ? "bg-white/10 font-medium text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {hours}h
            </button>
          ))}
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {forecast ? (
          <>
            <KpiCard
              label="Output now"
              value={forecast.current.output_kw}
              scale={1000}
              decimals={1}
              unit="MW"
              accent={accent}
              hint={`${(forecast.current.capacity_factor * 100).toFixed(0)}% of ${mw(
                forecast.capacity_kw,
                0,
              )} nameplate`}
            />
            <KpiCard
              label="Generated today"
              value={forecast.today_generated_kwh}
              scale={1000}
              decimals={0}
              unit="MWh"
              accent="neutral"
              hint="Recorded output since 00:00 UTC"
              delay={0.05}
            />
            <KpiCard
              label="Peak in horizon"
              value={Math.max(
                ...forecast.forecast.slice(0, horizon).map((point) => point.predicted_kw),
                0,
              )}
              scale={1000}
              decimals={1}
              unit="MW"
              accent={forecast.alert_summary.by_type.over_generation > 0 ? "danger" : "ok"}
              hint={
                forecast.export_limit_kw < forecast.capacity_kw
                  ? `Export limit ${mw(forecast.export_limit_kw, 0)}`
                  : `Over-gen trigger at 85% of nameplate`
              }
              delay={0.1}
            />
            <KpiCard
              label="Forecast confidence"
              value={forecast.model.confidence_pct}
              decimals={1}
              unit="%"
              accent="ok"
              hint={`Mean 80% band is ${forecast.model.band_width_pct_capacity.toFixed(
                1,
              )}% of capacity over 24 h`}
              delay={0.15}
            />
          </>
        ) : (
          Array.from({ length: 4 }).map((_, i) => <KpiSkeleton key={i} />)
        )}
      </section>

      <section className="glass p-4 sm:p-5">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 className="font-semibold text-white">Generation forecast</h2>
            <p className="text-xs text-slate-400">
              Recorded output and the next {horizon} hours, with flagged risk windows shaded in
              place.
            </p>
          </div>
          {forecast && forecast.alert_summary.total > 0 && (
            <span className="text-xs text-slate-400">
              {forecast.alert_summary.total} flagged window
              {forecast.alert_summary.total === 1 ? "" : "s"}
            </span>
          )}
        </div>
        {forecast ? (
          <ForecastChart data={forecast} horizon={horizon} />
        ) : (
          <Skeleton className="h-[420px] w-full" />
        )}
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="glass p-4 sm:p-5">
          <h2 className="mb-1 font-semibold text-white">Recommended actions</h2>
          <p className="mb-3.5 text-xs text-slate-400">
            Each reason is assembled from this site&apos;s forecast, limits and battery state — not
            a template.
          </p>
          {forecast ? (
            <RecommendationPanel recommendations={forecast.recommendations} limit={6} />
          ) : (
            <div className="space-y-3">
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="glass p-4 sm:p-5">
            <div className="mb-1 flex items-baseline justify-between gap-3">
              <h2 className="font-semibold text-white">Yesterday&apos;s forecast vs actual</h2>
              {backtest?.accuracy.available && (
                <span className="font-mono text-xs text-ok">
                  MAE {backtest.accuracy.mae_pct_capacity?.toFixed(2)}%
                </span>
              )}
            </div>
            <p className="mb-2 text-xs leading-relaxed text-slate-400">
              A rolling day-ahead replay: for each day we rewind, hand the model only what it knew
              that morning, and let it run 24 h unaided.
            </p>
            {backtest && forecast ? (
              <>
                <BacktestChart data={backtest} siteType={forecast.site_type} compact />
                <div className="mt-2 grid grid-cols-3 gap-3 border-t border-white/[0.07] pt-3">
                  <MiniStat
                    label="MAE"
                    value={
                      backtest.accuracy.mae_kw !== undefined ? mw(backtest.accuracy.mae_kw) : "—"
                    }
                  />
                  <MiniStat
                    label="RMSE"
                    value={
                      backtest.accuracy.rmse_kw !== undefined ? mw(backtest.accuracy.rmse_kw) : "—"
                    }
                  />
                  <MiniStat
                    label="R²"
                    value={
                      backtest.accuracy.r2 !== null && backtest.accuracy.r2 !== undefined
                        ? backtest.accuracy.r2.toFixed(3)
                        : "—"
                    }
                  />
                </div>
              </>
            ) : (
              <Skeleton className="h-[200px] w-full" />
            )}
          </div>

          <div className="glass p-4 sm:p-5">
            <h2 className="mb-1 font-semibold text-white">Weather driving the forecast</h2>
            <p className="mb-3 text-xs text-slate-400">
              Current conditions at the site, from Open-Meteo.
            </p>
            {forecast ? <WeatherPanel data={forecast} /> : <Skeleton className="h-40 w-full" />}
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="glass p-4 sm:p-5">
          <h2 className="mb-3 font-semibold text-white">Flagged windows</h2>
          {forecast ? (
            <AlertTimeline alerts={forecast.alerts} />
          ) : (
            <Skeleton className="h-40 w-full" />
          )}
        </div>

        {site && forecast && <SiteConfigPanel site={site} forecast={forecast} />}
      </section>
    </div>
  );
}

function SiteConfigPanel({ site, forecast }: { site: Site; forecast: SiteForecast }) {
  const constrained = site.export_limit_kw > 0 && site.export_limit_kw < site.capacity_kw;
  const socPct = site.storage_capacity_kwh
    ? (site.storage_soc_kwh / site.storage_capacity_kwh) * 100
    : 0;

  return (
    <div className="glass space-y-3 p-4 sm:p-5">
      <div>
        <h2 className="font-semibold text-white">Site configuration</h2>
        <p className="mt-1 text-xs leading-relaxed text-slate-400">
          The numbers the rule engine compares the forecast against. Change these and every alert
          and recommendation on this page moves with them.
        </p>
      </div>

      <dl className="divide-y divide-white/[0.06] text-sm">
        <ConfigRow label="Nameplate capacity" value={mw(site.capacity_kw, 0)} />
        <ConfigRow
          label="Grid export limit"
          value={constrained ? mw(site.export_limit_kw, 0) : "Unconstrained"}
          note={
            constrained
              ? `${((site.export_limit_kw / site.capacity_kw) * 100).toFixed(0)}% of nameplate — surplus above this has to be stored or curtailed`
              : undefined
          }
        />
        {site.firm_commitment_kw > 0 && (
          <ConfigRow
            label="Firm delivery schedule"
            value={mw(site.firm_commitment_kw, 0)}
            note={`Contracted for ${String(site.commitment_start_hour_utc).padStart(
              2,
              "0",
            )}:00–${String(site.commitment_end_hour_utc).padStart(2, "0")}:00 UTC`}
          />
        )}
        <ConfigRow
          label="Over-generation trigger"
          value={`${(site.over_threshold * 100).toFixed(0)}% of ${
            constrained ? "export limit" : "nameplate"
          }`}
          note={mw(site.over_threshold * (constrained ? site.export_limit_kw : site.capacity_kw))}
        />
        <ConfigRow
          label="Under-generation floor"
          value={`${(site.under_threshold * 100).toFixed(0)}% of nameplate`}
          note={mw(site.under_threshold * site.capacity_kw)}
        />
        <ConfigRow
          label="Ramp trigger"
          value={`${(site.ramp_threshold * 100).toFixed(0)}% per hour`}
          note={`${mw(site.ramp_threshold * site.capacity_kw)} swing hour-over-hour`}
        />
        <ConfigRow
          label="Co-located storage"
          value={site.storage_capacity_kwh > 0 ? mwh(site.storage_capacity_kwh, 0) : "None"}
          note={
            site.storage_capacity_kwh > 0
              ? `${socPct.toFixed(0)}% charged · ${mwh(
                  site.storage_capacity_kwh - site.storage_soc_kwh,
                  0,
                )} headroom`
              : undefined
          }
        />
        <ConfigRow
          label="Model"
          value={forecast.model.algorithm}
          note={
            forecast.model.mae_pct_capacity
              ? `Held-out MAE ${forecast.model.mae_pct_capacity.toFixed(2)}% of capacity`
              : undefined
          }
        />
      </dl>
    </div>
  );
}

function ConfigRow({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5">
      <dt className="text-slate-400">{label}</dt>
      <dd className="text-right">
        <span className="font-mono text-slate-100">{value}</span>
        {note && <div className="mt-0.5 text-[11px] leading-snug text-slate-500">{note}</div>}
      </dd>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="mt-0.5 font-mono text-sm tabular-nums text-slate-100">{value}</div>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/"
      className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200"
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M19 12H5m6 6-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Portfolio
    </Link>
  );
}
