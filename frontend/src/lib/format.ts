// Formatting helpers. Power is displayed in MW throughout -- the backend speaks
// kW because that's what plant data uses, but nobody says "180,000 kilowatts".

export function mw(kw: number, digits = 1): string {
  return `${(kw / 1000).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} MW`;
}

export function mwh(kwh: number, digits = 1): string {
  return `${(kwh / 1000).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} MWh`;
}

export function pct(fraction: number, digits = 0): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

// Everything on screen is UTC, because grid operations are and because the
// backend builds its reason strings in UTC. Letting the browser localise
// timestamps would put "Sat 11:30" on a card whose own sentence says
// "06:00-10:00 UTC" -- the two would disagree by the reader's offset.
const UTC = { timeZone: "UTC" } as const;

/** "Tue 14:00" -- short enough for a dense axis, unambiguous across a 72h span. */
export function shortTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    ...UTC,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function hourLabel(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    ...UTC,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function dayLabel(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    ...UTC,
    day: "numeric",
    month: "short",
  });
}

export function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

/** The window an alert or recommendation covers, e.g. "Fri 06:00 - 10:00". */
export function windowLabel(start: string, end: string): string {
  const from = new Date(start);
  const to = new Date(end);
  const sameDay = from.toISOString().slice(0, 10) === to.toISOString().slice(0, 10);
  return sameDay
    ? `${shortTime(start)} - ${hourLabel(end)}`
    : `${shortTime(start)} - ${shortTime(end)}`;
}
