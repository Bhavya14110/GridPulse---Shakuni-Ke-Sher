"""Flag the hours a control room needs to do something about.

Deliberately rule-based, not learned. An operator who is about to curtail a
180 MW park needs to see *why*, and "the model said so" is not an answer. Every
flag here is a comparison between two numbers we can both put on screen.

Three rules, straight out of the problem statement:

  over-generation   forecast output exceeds what the grid connection will take
  under-generation  forecast output falls short of what the site owes
  ramp              output swings hard enough hour-over-hour to eat reserve

The nuance is in what each rule compares against, which is per-site:

  * over-generation is measured against the **export limit**, not nameplate. A
    plant that can make 180 MW behind a 95 MW substation is over-generating at
    81 MW, however much headroom the panels still have.
  * under-generation is measured against the higher of the site's low-output
    threshold and its **firm delivery schedule**. A plant that sold 45 MW
    day-ahead is short at 30 MW even though 30 MW is a perfectly healthy output.
  * a site with a delivery schedule is only judged inside the block of hours
    it actually sold. A solar site *without* one is only judged when the sun is
    high enough that it should have been producing -- the clear-sky potential
    tells us the difference between "it's evening" and "a cloud bank parked
    over the array", and only the second is worth waking someone up for.
"""
from __future__ import annotations

from datetime import datetime

# An hour-long dip doesn't need a backup plant spun up; a three-hour one does.
MIN_SUSTAINED_HOURS = 2

# Solar with no delivery schedule: only flag low output when the site *could*
# have been producing this much of nameplate under clear skies.
SOLAR_PRODUCTIVE_POTENTIAL = 0.40


def _parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def _group_consecutive(rows: list[dict]) -> list[list[dict]]:
    """Collapse individually-flagged hours into contiguous windows."""
    windows: list[list[dict]] = []
    for row in rows:
        if windows and row["hours_ahead"] == windows[-1][-1]["hours_ahead"] + 1:
            windows[-1].append(row)
        else:
            windows.append([row])
    return windows


_LEVELS = ["info", "warning", "critical"]

# A long event is a harder operational problem than a big brief one: four hours
# of mild shortfall still means four hours of replacement power to find.
SUSTAINED_ESCALATION_HOURS = 4


def _severity(fraction_of_reference: float, duration_hours: int = 1) -> str:
    """How loudly to shout, scaled by how much power is at stake and for how long."""
    if fraction_of_reference >= 0.20:
        level = 2
    elif fraction_of_reference >= 0.08:
        level = 1
    else:
        level = 0

    if duration_hours >= SUSTAINED_ESCALATION_HOURS:
        level = min(level + 1, 2)
    return _LEVELS[level]


def _window_id(site_id: int, kind: str, window: list[dict]) -> str:
    stamp = _parse(window[0]["timestamp"]).strftime("%Y%m%dT%H%M")
    return f"s{site_id}-{kind}-{stamp}"


def _hours_label(window: list[dict]) -> str:
    start = _parse(window[0]["timestamp"])
    end = _parse(window[-1]["timestamp"])
    if start == end:
        return start.strftime("%d %b %H:%M UTC")
    return f"{start:%d %b %H:%M}-{end:%H:%M} UTC"


def detect_alerts(site, forecast_payload: dict) -> list[dict]:
    """Run all three rules over a site's forward forecast."""
    rows = forecast_payload.get("forecast", [])
    if not rows:
        return []

    capacity = float(site.capacity_kw)
    export_limit = float(site.effective_export_limit_kw)
    over_limit_kw = site.over_threshold * export_limit
    floor_from_threshold = site.under_threshold * capacity
    under_floor_kw = max(floor_from_threshold, float(site.firm_commitment_kw))
    ramp_limit_kw = site.ramp_threshold * capacity

    alerts: list[dict] = []
    alerts += _over_generation(site, rows, over_limit_kw, export_limit, capacity)
    alerts += _under_generation(site, rows, under_floor_kw, floor_from_threshold, capacity)
    alerts += _ramp_events(site, rows, ramp_limit_kw, capacity)

    order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (order[a["severity"]], a["start"]))
    return alerts


def _over_generation(site, rows, over_limit_kw, export_limit, capacity) -> list[dict]:
    flagged = [r for r in rows if r["predicted_kw"] > over_limit_kw]
    alerts = []
    for window in _group_consecutive(flagged):
        if len(window) < MIN_SUSTAINED_HOURS:
            continue
        peak = max(r["predicted_kw"] for r in window)
        # Energy that physically has nowhere to go, hour by hour.
        surplus_kwh = sum(r["predicted_kw"] - export_limit for r in window if r["predicted_kw"] > export_limit)
        peak_surplus = max(peak - export_limit, 0.0)
        constrained = export_limit < capacity

        reference = (
            f"the {export_limit / 1000:,.0f} MW substation export limit"
            if constrained
            else f"{capacity / 1000:,.0f} MW nameplate"
        )
        alerts.append(
            {
                "id": _window_id(site.id, "over", window),
                "type": "over_generation",
                # What matters is the power you'd actually have to shed, measured
                # against the limit that's binding for this site.
                "severity": _severity(
                    max(peak_surplus, peak - over_limit_kw) / export_limit, len(window)
                ),
                "start": window[0]["timestamp"],
                "end": window[-1]["timestamp"],
                "duration_hours": len(window),
                "peak_kw": round(peak, 1),
                "threshold_kw": round(over_limit_kw, 1),
                "reference_kw": round(export_limit, 1),
                "reference_label": "export_limit" if constrained else "capacity",
                "surplus_kwh": round(surplus_kwh, 1),
                "peak_surplus_kw": round(peak_surplus, 1),
                "peak_pct_of_reference": round(peak / export_limit * 100, 1),
                "headline": f"Over-generation risk - {_hours_label(window)}",
                "detail": (
                    f"Forecast peaks at {peak / 1000:,.1f} MW across {len(window)}h, "
                    f"{peak / export_limit * 100:.0f}% of {reference} and above the "
                    f"{site.over_threshold:.0%} over-generation trigger "
                    f"({over_limit_kw / 1000:,.1f} MW)."
                ),
            }
        )
    return alerts


def _under_generation(site, rows, under_floor_kw, floor_from_threshold, capacity) -> list[dict]:
    has_commitment = site.firm_commitment_kw > 0
    start_hour = int(site.commitment_start_hour_utc)
    end_hour = int(site.commitment_end_hour_utc)

    def in_window(row: dict) -> bool:
        if has_commitment:
            # Inside a contracted block, being short is a problem regardless of
            # why -- the power was sold and somebody has to deliver it.
            hour = _parse(row["timestamp"]).hour
            return start_hour <= hour < end_hour
        if site.site_type != "solar":
            return True
        return row["potential_kw"] >= SOLAR_PRODUCTIVE_POTENTIAL * capacity

    flagged = [r for r in rows if in_window(r) and r["predicted_kw"] < under_floor_kw]
    alerts = []
    for window in _group_consecutive(flagged):
        if len(window) < MIN_SUSTAINED_HOURS:
            continue
        trough = min(r["predicted_kw"] for r in window)
        shortfall_kwh = sum(under_floor_kw - r["predicted_kw"] for r in window)
        peak_shortfall = under_floor_kw - trough
        binding = "delivery schedule" if under_floor_kw > floor_from_threshold else "low-output threshold"

        if binding == "delivery schedule":
            because = (
                f"against a {site.firm_commitment_kw / 1000:,.0f} MW firm delivery schedule"
            )
        else:
            because = (
                f"below the {site.under_threshold:.0%}-of-capacity floor "
                f"({under_floor_kw / 1000:,.1f} MW)"
            )

        alerts.append(
            {
                "id": _window_id(site.id, "under", window),
                "type": "under_generation",
                # Scale the gap against what was expected of the asset. Flooring
                # the denominator at a quarter of nameplate stops a site with a
                # tiny threshold from calling every 4 MW wobble a crisis.
                "severity": _severity(
                    peak_shortfall / max(under_floor_kw, 0.25 * capacity), len(window)
                ),
                "start": window[0]["timestamp"],
                "end": window[-1]["timestamp"],
                "duration_hours": len(window),
                "trough_kw": round(trough, 1),
                "threshold_kw": round(under_floor_kw, 1),
                "reference_label": binding,
                "shortfall_kwh": round(shortfall_kwh, 1),
                "peak_shortfall_kw": round(peak_shortfall, 1),
                "headline": f"Under-generation risk - {_hours_label(window)}",
                "detail": (
                    f"Forecast bottoms out at {trough / 1000:,.1f} MW across {len(window)}h, "
                    f"{because} - a {peak_shortfall / 1000:,.1f} MW gap at its worst "
                    f"and {shortfall_kwh / 1000:,.0f} MWh over the window."
                ),
            }
        )
    return alerts


def _ramp_events(site, rows, ramp_limit_kw, capacity) -> list[dict]:
    """Hour-over-hour swings big enough to matter for reserve scheduling.

    Consecutive hours ramping the same way are one event, not three. A front
    coming through a wind farm over four hours is a single thing an operator
    schedules against, and reporting it three times just buries the other alerts.
    """
    steps = []
    for previous, current in zip(rows, rows[1:]):
        delta = current["predicted_kw"] - previous["predicted_kw"]
        if abs(delta) >= ramp_limit_kw:
            steps.append({"from": previous, "to": current, "delta": delta})

    # Group by run of same-signed, back-to-back steps.
    runs: list[list[dict]] = []
    for step in steps:
        contiguous = (
            runs
            and runs[-1][-1]["to"]["hours_ahead"] == step["from"]["hours_ahead"]
            and (runs[-1][-1]["delta"] > 0) == (step["delta"] > 0)
        )
        if contiguous:
            runs[-1].append(step)
        else:
            runs.append([step])

    alerts = []
    for run in runs:
        first, last = run[0]["from"], run[-1]["to"]
        total_delta = last["predicted_kw"] - first["predicted_kw"]
        steepest = max(abs(step["delta"]) for step in run)
        rising = total_delta > 0
        kind = "ramp_up" if rising else "ramp_down"
        hours = len(run)
        span = f"over {hours}h" if hours > 1 else "in one hour"

        alerts.append(
            {
                "id": _window_id(site.id, kind, [first]),
                "type": kind,
                "severity": _severity(steepest / capacity, hours),
                "start": first["timestamp"],
                "end": last["timestamp"],
                "duration_hours": hours,
                "delta_kw": round(total_delta, 1),
                "steepest_hourly_kw": round(steepest, 1),
                "from_kw": round(first["predicted_kw"], 1),
                "to_kw": round(last["predicted_kw"], 1),
                "threshold_kw": round(ramp_limit_kw, 1),
                "pct_of_capacity_per_hour": round(steepest / capacity * 100, 1),
                "headline": (
                    f"{'Upward' if rising else 'Downward'} ramp - "
                    f"{_hours_label([first, last])}"
                ),
                "detail": (
                    f"Output swings {'up' if rising else 'down'} "
                    f"{abs(total_delta) / 1000:,.1f} MW {span} "
                    f"({first['predicted_kw'] / 1000:,.1f} -> {last['predicted_kw'] / 1000:,.1f} MW), "
                    f"peaking at {steepest / capacity * 100:.0f}% of capacity in a single hour "
                    f"against a {site.ramp_threshold:.0%} ramp trigger."
                ),
            }
        )
    return alerts


def summarize(alerts: list[dict]) -> dict:
    """Counts the portfolio view needs, without re-deriving them client-side."""
    return {
        "total": len(alerts),
        "critical": sum(1 for a in alerts if a["severity"] == "critical"),
        "warning": sum(1 for a in alerts if a["severity"] == "warning"),
        "info": sum(1 for a in alerts if a["severity"] == "info"),
        "by_type": {
            kind: sum(1 for a in alerts if a["type"] == kind)
            for kind in ("over_generation", "under_generation", "ramp_up", "ramp_down")
        },
        "status": (
            "critical"
            if any(a["severity"] == "critical" for a in alerts)
            else "warning"
            if any(a["severity"] == "warning" for a in alerts)
            else "normal"
        ),
    }
