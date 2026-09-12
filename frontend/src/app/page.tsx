"use client";

import { motion } from "framer-motion";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AddSiteDialog } from "@/components/AddSiteDialog";
import { KpiCard } from "@/components/KpiCard";
import { RecommendationPanel } from "@/components/RecommendationPanel";
import { SiteCard } from "@/components/SiteCard";
import { ErrorState, KpiSkeleton, Skeleton } from "@/components/Skeleton";
import { api } from "@/lib/api";
import { mwh, relativeTime } from "@/lib/format";
import type { PortfolioSummary, Recommendation } from "@/lib/types";

// Leaflet touches `window` at import time, so it can only load in the browser.
const PortfolioMap = dynamic(
  () => import("@/components/PortfolioMap").then((mod) => mod.PortfolioMap),
  {
    ssr: false,
    loading: () => <Skeleton className="h-full w-full" />,
  },
);

export default function PortfolioPage() {
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setError(null);
      const summary = await api.portfolio();
      setData(summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    // The backend refreshes its own cache every 15 min; polling at 2 min keeps
    // the dashboard in step without hammering it.
    const timer = setInterval(() => void load(), 120_000);
    return () => clearInterval(timer);
  }, [load]);

  // The portfolio-wide action queue: every site's recommendations, most urgent
  // first, so an operator sees the whole estate in one list.
  const queue: Recommendation[] = useMemo(() => {
    if (!data) return [];
    const rank = { critical: 0, warning: 1, info: 2 } as const;
    return data.sites
      .map((site) => site.top_recommendation)
      .filter((rec): rec is Recommendation => Boolean(rec))
      .sort(
        (a, b) =>
          rank[a.severity] - rank[b.severity] || a.window_start.localeCompare(b.window_start),
      );
  }, [data]);

  if (error && !data) {
    return (
      <div className="pt-6">
        <ErrorState message={error} onRetry={() => void load()} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <motion.h1
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="text-2xl font-semibold tracking-tight text-white sm:text-[28px]"
          >
            Portfolio overview
          </motion.h1>
          <p className="mt-1 text-sm text-slate-400">
            72-hour generation forecast, risk windows and recommended grid actions across{" "}
            {data?.site_count ?? "…"} sites.
            {data && (
              <span className="ml-1.5 text-slate-500">
                Updated {relativeTime(data.generated_at)}.
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <AddSiteDialog onCreated={() => void load()} />
          <button
            onClick={() => void load()}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-slate-200 transition-colors hover:bg-white/10"
          >
            <RefreshIcon /> Refresh
          </button>
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {loading && !data ? (
          Array.from({ length: 5 }).map((_, i) => <KpiSkeleton key={i} />)
        ) : data ? (
          <>
            <KpiCard
              label="Capacity online"
              value={data.total_capacity_kw}
              scale={1000}
              decimals={0}
              unit="MW"
              accent="neutral"
              hint={`${data.site_count} sites across the portfolio`}
              delay={0}
            />
            <KpiCard
              label="Generating now"
              value={data.current_output_kw}
              scale={1000}
              decimals={1}
              unit="MW"
              accent="solar"
              hint={`${(data.portfolio_capacity_factor * 100).toFixed(0)}% of nameplate`}
              delay={0.05}
            />
            <KpiCard
              label="Forecast next 24 h"
              value={data.forecast_24h_mwh}
              decimals={0}
              unit="MWh"
              accent="wind"
              hint="Sum of hourly predictions across all sites"
              delay={0.1}
            />
            <KpiCard
              label="Sites needing action"
              value={data.sites_with_alerts}
              accent={data.alert_counts.critical > 0 ? "danger" : "ok"}
              hint={`${data.alert_counts.critical} critical · ${data.alert_counts.warning} warning`}
              delay={0.15}
            />
            <KpiCard
              label="Curtailment avoidable"
              value={data.curtailment_avoidable_mwh}
              decimals={0}
              unit="MWh"
              accent="ok"
              hint={`Storage can absorb this much of the ${mwh(
                data.curtailment_at_risk_mwh * 1000,
                0,
              )} at risk`}
              delay={0.2}
            />
          </>
        ) : null}
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <motion.div
          initial={{ opacity: 0, scale: 0.99 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="glass relative h-[460px] overflow-hidden p-1.5"
        >
          {data ? <PortfolioMap sites={data.sites} /> : <Skeleton className="h-full w-full" />}
          <MapLegend />
        </motion.div>

        <div className="glass flex h-[460px] flex-col p-4">
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <div>
              <h2 className="font-semibold text-white">Action queue</h2>
              <p className="text-[11px] text-slate-500">
                Most urgent action per site — open a site for its full list
              </p>
            </div>
            <span className="shrink-0 text-xs text-slate-400">
              {queue.length} {queue.length === 1 ? "site" : "sites"}
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            {data ? (
              <RecommendationPanel recommendations={queue} />
            ) : (
              <div className="space-y-3">
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
              </div>
            )}
          </div>
        </div>
      </section>

      <section>
        <h2 className="mb-3 font-semibold text-white">Sites</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data
            ? data.sites.map((site, index) => (
                <SiteCard key={site.id} site={site} index={index} />
              ))
            : Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-56 w-full" />)}
        </div>
      </section>

      {data && <ModelStrip data={data} />}
    </div>
  );
}

function ModelStrip({ data }: { data: PortfolioSummary }) {
  const solarMae = data.model.solar?.["mae_pct_capacity"] as number | undefined;
  const windMae = data.model.wind?.["mae_pct_capacity"] as number | undefined;
  const solarGain = data.model.solar?.["improvement_over_persistence_pct"] as number | undefined;

  return (
    <motion.section
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5, delay: 0.2 }}
      className="glass flex flex-wrap items-center gap-x-8 gap-y-3 p-4 text-sm"
    >
      <div>
        <div className="label">Forecast model</div>
        <div className="mt-0.5 text-slate-200">XGBoost, one per technology</div>
      </div>
      <Stat label="Solar MAE" value={solarMae ? `${solarMae.toFixed(2)}%` : "—"} sub="of capacity" />
      <Stat label="Wind MAE" value={windMae ? `${windMae.toFixed(2)}%` : "—"} sub="of capacity" />
      <Stat
        label="vs persistence"
        value={solarGain ? `${solarGain.toFixed(0)}% better` : "—"}
        sub="held-out hours"
      />
      <Stat
        label="Trained on"
        value={data.model.dataset_rows ? `${(data.model.dataset_rows / 1000).toFixed(0)}k hours` : "—"}
        sub={data.model.dataset_span ? data.model.dataset_span.join(" → ") : ""}
      />
      <a
        href="/model"
        className="ml-auto rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200 transition-colors hover:bg-white/10"
      >
        Full model report →
      </a>
    </motion.section>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="mt-0.5 font-mono font-semibold tabular-nums text-white">{value}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}

function MapLegend() {
  return (
    <div className="pointer-events-none absolute bottom-4 left-4 z-[500] flex flex-col gap-1.5 rounded-xl border border-white/10 bg-base-900/85 px-3 py-2.5 text-[11px] backdrop-blur-md">
      <span className="label">Site status</span>
      <Dot color="#f87171">Action required</Dot>
      <Dot color="#fbbf24">Watch</Dot>
      <Dot color="#34d399">Nominal</Dot>
    </div>
  );
}

function Dot({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-2 text-slate-300">
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      {children}
    </span>
  );
}

function RefreshIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.9}>
      <path d="M21 12a9 9 0 1 1-3-6.7M21 3v6h-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
