import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Deep slate base -- a control room runs dark because operators stare
        // at it for twelve hours.
        base: {
          900: "#070b14",
          800: "#0b1120",
          700: "#111a2e",
          600: "#18253d",
          500: "#22324f",
        },
        // Technology accents: amber reads as sun, cyan as wind. Used
        // consistently so you can tell a solar chart from a wind one at a
        // glance without reading the label.
        solar: { DEFAULT: "#fbbf24", deep: "#f59e0b", glow: "#fcd34d" },
        wind: { DEFAULT: "#22d3ee", deep: "#06b6d4", glow: "#67e8f9" },
        danger: { DEFAULT: "#f87171", deep: "#ef4444" },
        caution: { DEFAULT: "#fbbf24", deep: "#f59e0b" },
        ok: { DEFAULT: "#34d399", deep: "#10b981" },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glass: "0 1px 0 0 rgba(255,255,255,0.05) inset, 0 18px 40px -24px rgba(0,0,0,0.9)",
        glow: "0 0 28px -6px var(--tw-shadow-color)",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "70%": { transform: "scale(1.6)", opacity: "0" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        shimmer: "shimmer 1.8s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
