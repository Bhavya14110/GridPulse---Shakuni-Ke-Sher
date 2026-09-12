import type { Severity, SiteStatus } from "@/lib/types";

const STATUS_STYLES: Record<SiteStatus, { dot: string; text: string; ring: string; label: string }> =
  {
    critical: {
      dot: "bg-danger",
      text: "text-danger",
      ring: "ring-danger/30 bg-danger/10",
      label: "Action required",
    },
    warning: {
      dot: "bg-caution",
      text: "text-caution",
      ring: "ring-caution/30 bg-caution/10",
      label: "Watch",
    },
    normal: {
      dot: "bg-ok",
      text: "text-ok",
      ring: "ring-ok/30 bg-ok/10",
      label: "Nominal",
    },
    unavailable: {
      dot: "bg-slate-500",
      text: "text-slate-400",
      ring: "ring-slate-500/30 bg-slate-500/10",
      label: "No data",
    },
  };

export function StatusPill({ status, label }: { status: SiteStatus; label?: string }) {
  const style = STATUS_STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ${style.ring} ${style.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {label ?? style.label}
    </span>
  );
}

export const SEVERITY_STYLES: Record<Severity, { text: string; bg: string; border: string; bar: string }> =
  {
    critical: {
      text: "text-danger",
      bg: "bg-danger/10",
      border: "border-danger/30",
      bar: "bg-danger",
    },
    warning: {
      text: "text-caution",
      bg: "bg-caution/10",
      border: "border-caution/30",
      bar: "bg-caution",
    },
    info: {
      text: "text-wind",
      bg: "bg-wind/10",
      border: "border-wind/25",
      bar: "bg-wind",
    },
  };

export function SeverityTag({ severity }: { severity: Severity }) {
  const style = SEVERITY_STYLES[severity];
  return (
    <span
      className={`rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${style.border} ${style.bg} ${style.text}`}
    >
      {severity}
    </span>
  );
}
