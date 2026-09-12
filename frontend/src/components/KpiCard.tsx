"use client";

import { motion } from "framer-motion";

import { AnimatedNumber } from "./AnimatedNumber";

interface Props {
  label: string;
  value: number;
  unit?: string;
  decimals?: number;
  scale?: number;
  hint?: string;
  accent?: "solar" | "wind" | "danger" | "ok" | "neutral";
  icon?: React.ReactNode;
  delay?: number;
}

const ACCENTS = {
  solar: { text: "text-solar", glow: "from-solar/20", ring: "ring-solar/20" },
  wind: { text: "text-wind", glow: "from-wind/20", ring: "ring-wind/20" },
  danger: { text: "text-danger", glow: "from-danger/20", ring: "ring-danger/20" },
  ok: { text: "text-ok", glow: "from-ok/20", ring: "ring-ok/20" },
  neutral: { text: "text-slate-200", glow: "from-white/10", ring: "ring-white/10" },
};

export function KpiCard({
  label,
  value,
  unit,
  decimals = 0,
  scale = 1,
  hint,
  accent = "neutral",
  icon,
  delay = 0,
}: Props) {
  const style = ACCENTS[accent];
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.16, 1, 0.3, 1] }}
      className="glass glass-hover relative overflow-hidden p-4"
    >
      <div
        className={`pointer-events-none absolute -right-10 -top-14 h-32 w-32 rounded-full bg-gradient-to-br ${style.glow} to-transparent blur-2xl`}
      />
      <div className="relative flex items-start justify-between gap-3">
        <span className="label">{label}</span>
        {icon && <span className={`${style.text} opacity-80`}>{icon}</span>}
      </div>
      <div className="relative mt-2.5 flex items-baseline gap-1.5">
        <AnimatedNumber
          value={value}
          decimals={decimals}
          scale={scale}
          className={`metric ${style.text}`}
        />
        {unit && <span className="text-sm font-medium text-slate-400">{unit}</span>}
      </div>
      {hint && <p className="relative mt-1.5 text-xs leading-snug text-slate-400">{hint}</p>}
    </motion.div>
  );
}
