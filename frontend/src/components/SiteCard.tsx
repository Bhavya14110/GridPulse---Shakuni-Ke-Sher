"use client";

import { motion } from "framer-motion";
import Link from "next/link";

import { mw, mwh, pct } from "@/lib/format";
import type { PortfolioSite } from "@/lib/types";
import { StatusPill } from "./StatusPill";

export function SiteCard({ site, index }: { site: PortfolioSite; index: number }) {
  const isSolar = site.site_type === "solar";
  const accent = isSolar ? "text-solar" : "text-wind";
  const ring = isSolar ? "ring-solar/20" : "ring-wind/20";
  const glow = isSolar ? "from-solar/[0.14]" : "from-wind/[0.14]";
  const utilisation = Math.min(site.capacity_factor, 1);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: Math.min(index * 0.05, 0.35), ease: [0.16, 1, 0.3, 1] }}
    >
      <Link
        href={`/sites/${site.id}`}
        className="glass glass-hover group relative block overflow-hidden p-4"
      >
        <div
          className={`pointer-events-none absolute -right-12 -top-16 h-36 w-36 rounded-full bg-gradient-to-br ${glow} to-transparent blur-2xl`}
        />

        <div className="relative flex items-start gap-3">
          <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/5 ring-1 ${ring} ${accent}`}>
            {isSolar ? <SunIcon /> : <WindIcon />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="truncate font-semibold text-white">{site.name}</h3>
              {site.is_demo_site && (
                <span className="shrink-0 rounded border border-white/15 bg-white/5 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-300">
                  Hero site
                </span>
              )}
            </div>
            <p className="truncate text-xs text-slate-400">{site.region}</p>
          </div>
          <StatusPill status={site.status} />
        </div>

        <div className="relative mt-4 grid grid-cols-3 gap-3">
          <Metric label="Output now" value={mw(site.current_output_kw)} accent={accent} />
          <Metric label="Today" value={mwh(site.today_generated_kwh, 0)} />
          <Metric label="Nameplate" value={mw(site.capacity_kw, 0)} />
        </div>

        {/* Utilisation bar: the fastest read of "is this asset working hard". */}
        <div className="relative mt-3.5">
          <div className="mb-1 flex items-center justify-between text-[11px] text-slate-400">
            <span>Capacity utilisation</span>
            <span className="font-mono tabular-nums">{pct(site.capacity_factor)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${utilisation * 100}%` }}
              transition={{ duration: 0.9, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
              className={`h-full rounded-full ${isSolar ? "bg-solar" : "bg-wind"}`}
            />
          </div>
        </div>

        {site.top_recommendation ? (
          <div className="relative mt-3.5 border-t border-white/[0.07] pt-3">
            <div className="label mb-1">Next action</div>
            <p className="line-clamp-2 text-[13px] leading-snug text-slate-300">
              {site.top_recommendation.title}
            </p>
          </div>
        ) : (
          <div className="relative mt-3.5 border-t border-white/[0.07] pt-3">
            <p className="text-[13px] text-slate-500">No action needed in the next 72 h</p>
          </div>
        )}

        <span className="absolute bottom-4 right-4 translate-x-1 text-slate-500 opacity-0 transition-all duration-300 group-hover:translate-x-0 group-hover:opacity-100">
          <ArrowIcon />
        </span>
      </Link>
    </motion.div>
  );
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`mt-0.5 font-mono text-sm font-semibold tabular-nums ${accent ?? "text-slate-200"}`}>
        {value}
      </div>
    </div>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.8}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" strokeLinecap="round" />
    </svg>
  );
}

function WindIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.8}>
      <path d="M3 8h9a3 3 0 1 0-3-3M3 16h13a3 3 0 1 1-3 3M3 12h16" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M5 12h14m-6-6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
