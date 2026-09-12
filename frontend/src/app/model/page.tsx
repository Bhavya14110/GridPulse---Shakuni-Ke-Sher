"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ErrorState, Skeleton } from "@/components/Skeleton";
import { api } from "@/lib/api";

interface ModelReport {
  site_type: string;
  validation_rows: number;
  validation_span: [string, string];
  mae_pct_capacity: number;
  rmse_pct_capacity: number;
  r2: number;
  mae_kw: number;
  baseline_persistence_mae_pct_capacity: number;
  improvement_over_persistence_pct: number;
  top_features: { feature: string; importance: number }[];
}

interface Metrics {
  trained: boolean;
  message?: string;
  trained_at?: string;
  dataset_rows?: number;
  dataset_span?: [string, string];
  feature_columns?: string[];
  models?: Record<string, ModelReport>;
}

export default function ModelPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .metrics()
      .then((data) => setMetrics(data as unknown as Metrics))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!metrics) return <Skeleton className="h-80 w-full" />;

  if (!metrics.trained) {
    return (
      <ErrorState
        message={
          metrics.message ??
          "The models haven't been trained yet. Run the dataset build and training scripts in backend/ml."
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <Link
          href="/"
          className="mb-3 inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
            <path d="M19 12H5m6 6-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Portfolio
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-[28px]">
          Model report
        </h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-slate-400">
          These figures are read straight from the file the training run writes, so what&apos;s on
          this page is literally what the last training produced. Scores are on a{" "}
          <strong className="font-medium text-slate-300">chronological</strong> holdout — the most
          recent 20% of the record, never seen during training.
        </p>
      </header>

      <section className="glass flex flex-wrap gap-x-10 gap-y-4 p-5">
        <Fact label="Trained" value={metrics.trained_at ? new Date(metrics.trained_at).toLocaleString() : "—"} />
        <Fact
          label="Training rows"
          value={metrics.dataset_rows ? metrics.dataset_rows.toLocaleString() : "—"}
          sub="site-hours"
        />
        <Fact
          label="History covered"
          value={metrics.dataset_span ? `${metrics.dataset_span[0]} → ${metrics.dataset_span[1]}` : "—"}
          sub="ERA5 reanalysis weather"
        />
        <Fact label="Features" value={String(metrics.feature_columns?.length ?? 0)} sub="per hour" />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {Object.entries(metrics.models ?? {}).map(([type, report], index) => (
          <ModelCard key={type} type={type} report={report} index={index} />
        ))}
      </div>

      <section className="glass space-y-3 p-5 text-sm leading-relaxed text-slate-300">
        <h2 className="font-semibold text-white">Reading these numbers honestly</h2>
        <p>
          The R² figures are very high, and it&apos;s worth saying why rather than letting them
          speak for themselves. The training targets come from a physics model driven by real
          historical weather, plus a few percent of stochastic noise. The ML model is therefore
          learning a mapping that genuinely exists in the data — so it learns it well.
        </p>
        <p>
          Against real SCADA output, day-ahead solar forecasts typically land around 4–8% of
          capacity MAE, because real plants also have outages, soiling, inverter trips and grid
          curtailment that no weather feed predicts. Our numbers should be read as{" "}
          <em>the model has correctly learned the weather-to-power relationship</em>, not as{" "}
          <em>this would score this well on a real fleet</em>.
        </p>
        <p>
          The comparison that does transfer is the persistence baseline: predicting that the next
          hour looks like this one is what a control room falls back on without a model, and beating
          it by 75–80% on held-out hours is a real result. Swap the synthetic history for a CSV of
          actual SCADA data and nothing else in the pipeline needs to change.
        </p>
      </section>
    </div>
  );
}

function ModelCard({ type, report, index }: { type: string; report: ModelReport; index: number }) {
  const isSolar = type === "solar";
  const accent = isSolar ? "text-solar" : "text-wind";
  const bar = isSolar ? "bg-solar" : "bg-wind";
  const maxImportance = Math.max(...report.top_features.map((f) => f.importance), 0.0001);

  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: index * 0.08 }}
      className="glass p-5"
    >
      <div className="flex items-center justify-between">
        <h2 className={`text-lg font-semibold capitalize ${accent}`}>{type}</h2>
        <span className="text-xs text-slate-400">
          {report.validation_rows.toLocaleString()} held-out hours
        </span>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3">
        <BigStat label="MAE" value={`${report.mae_pct_capacity.toFixed(2)}%`} sub="of capacity" accent={accent} />
        <BigStat label="RMSE" value={`${report.rmse_pct_capacity.toFixed(2)}%`} sub="of capacity" />
        <BigStat label="R²" value={report.r2.toFixed(4)} sub="held out" />
      </div>

      <div className="mt-4 rounded-xl border border-white/[0.08] bg-white/[0.03] p-3">
        <div className="flex items-baseline justify-between text-sm">
          <span className="text-slate-300">vs. persistence baseline</span>
          <span className={`font-mono font-semibold ${accent}`}>
            {report.improvement_over_persistence_pct.toFixed(1)}% better
          </span>
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
          Persistence (assume next hour = this hour) scores{" "}
          {report.baseline_persistence_mae_pct_capacity.toFixed(2)}% MAE on the same hours; this
          model scores {report.mae_pct_capacity.toFixed(2)}%.
        </p>
      </div>

      <div className="mt-4">
        <div className="label mb-2">What the model leans on</div>
        <div className="space-y-1.5">
          {report.top_features.slice(0, 6).map((feature) => (
            <div key={feature.feature} className="flex items-center gap-2.5">
              <span className="w-40 shrink-0 truncate font-mono text-[11px] text-slate-400">
                {feature.feature}
              </span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${(feature.importance / maxImportance) * 100}%` }}
                  transition={{ duration: 0.7, delay: 0.2 }}
                  className={`h-full rounded-full ${bar}`}
                />
              </div>
              <span className="w-10 text-right font-mono text-[11px] tabular-nums text-slate-500">
                {(feature.importance * 100).toFixed(0)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </motion.section>
  );
}

function BigStat({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-3">
      <div className="label">{label}</div>
      <div className={`mt-1 font-mono text-xl font-semibold tabular-nums ${accent ?? "text-white"}`}>
        {value}
      </div>
      <div className="text-[11px] text-slate-500">{sub}</div>
    </div>
  );
}

function Fact({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="mt-0.5 font-mono text-sm text-white">{value}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}
