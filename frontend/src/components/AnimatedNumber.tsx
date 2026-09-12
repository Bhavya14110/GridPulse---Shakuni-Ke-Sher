"use client";

import { animate, useMotionValue, useTransform, motion } from "framer-motion";
import { useEffect } from "react";

interface Props {
  value: number;
  decimals?: number;
  /** Divide before display, e.g. 1000 to show kW as MW. */
  scale?: number;
  className?: string;
}

/**
 * Counts up to its value instead of snapping to it. Purely presentational, but
 * it makes a KPI row read as live telemetry rather than a static table -- and
 * it draws the eye to whichever number just changed on a refresh.
 */
export function AnimatedNumber({ value, decimals = 0, scale = 1, className }: Props) {
  const motionValue = useMotionValue(0);
  const display = useTransform(motionValue, (latest) =>
    (latest / scale).toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }),
  );

  useEffect(() => {
    const controls = animate(motionValue, value, {
      duration: 0.9,
      ease: [0.16, 1, 0.3, 1],
    });
    // Wrap rather than returning `controls.stop` directly: detached from its
    // instance it doesn't stop the animation properly, and under StrictMode's
    // double-mount that leaves the counter frozen at zero.
    return () => controls.stop();
  }, [value, motionValue]);

  return <motion.span className={className}>{display}</motion.span>;
}
