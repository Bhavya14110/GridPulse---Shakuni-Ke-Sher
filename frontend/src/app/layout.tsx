import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";
import { LiveClock } from "@/components/LiveClock";

export const metadata: Metadata = {
  title: "GridPulse — Renewable Generation Intelligence",
  description:
    "72-hour solar and wind generation forecasting with automatic risk flagging and explainable grid-action recommendations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="sticky top-0 z-[900] border-b border-white/10 bg-base-900/80 backdrop-blur-xl">
          <div className="mx-auto flex max-w-[1600px] items-center gap-4 px-5 py-3 sm:px-8">
            <Link href="/" className="group flex items-center gap-3">
              <PulseMark />
              <div className="leading-tight">
                <div className="text-lg font-semibold tracking-tight text-white">
                  Grid<span className="text-solar">Pulse</span>
                </div>
                <div className="hidden text-[11px] tracking-wide text-slate-400 sm:block">
                  Renewable Generation Intelligence
                </div>
              </div>
            </Link>

            <nav className="ml-4 hidden items-center gap-1 md:flex">
              <NavLink href="/">Portfolio</NavLink>
              <NavLink href="/model">Model</NavLink>
            </nav>

            <div className="ml-auto flex items-center gap-4">
              <LiveClock />
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-[1600px] px-5 pb-16 pt-6 sm:px-8">{children}</main>

        <footer className="border-t border-white/10 px-5 py-6 sm:px-8">
          <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-500">
            <span>
              Weather from{" "}
              <a
                className="text-slate-400 underline-offset-2 hover:underline"
                href="https://open-meteo.com/"
                target="_blank"
                rel="noreferrer"
              >
                Open-Meteo
              </a>{" "}
              · forecasts from an XGBoost model trained on physics-derived history
            </span>
            <span className="ml-auto">All times UTC</span>
          </div>
        </footer>
      </body>
    </html>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="rounded-lg px-3 py-1.5 text-sm text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
    >
      {children}
    </Link>
  );
}

/** The mark: a stylised power-curve pulse, warm-to-cool like the two technologies. */
function PulseMark() {
  return (
    <span className="relative grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-solar/25 to-wind/25 ring-1 ring-white/15">
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" strokeWidth={2.1}>
        <defs>
          <linearGradient id="pulse-mark" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="#fbbf24" />
            <stop offset="100%" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
        <path
          d="M2 15h3.2l2.4-7 3 12 2.6-9 2.2 4H22"
          stroke="url(#pulse-mark)"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
