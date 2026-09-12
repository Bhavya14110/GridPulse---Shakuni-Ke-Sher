"""Turn flagged risk windows into grid actions an operator can actually take.

Rule-based and fully traceable on purpose. Each recommendation carries a
`reason` string assembled from the same numbers the chart is drawing -- the
forecast MW, the limit it crosses, the battery's real state of charge, the MWh
at stake. Nothing here is a canned sentence with a number dropped into it; if
the forecast changes, the sentence changes with it.

The mapping follows the problem statement:

    over-generation  + no storage headroom   -> curtail
    over-generation  + storage headroom      -> charge the battery instead
    under-generation                         -> backup / import, sized to the gap
    sharp ramp down                          -> spinning reserve
    sharp ramp up                            -> confirm the grid can absorb it

What makes the storage branch worth something is that it's quantitative: we work
out how many MWh the surplus actually is and how many the battery can actually
take, and if the battery only covers part of it we recommend *both* -- charge
what fits, curtail the rest. That's the real answer, and it's the one an
operator would give.
"""
from __future__ import annotations

from datetime import datetime

# Round-trip losses mean a battery absorbs a bit less than the surplus delivers.
STORAGE_CHARGE_EFFICIENCY = 0.92

ACTION_PRIORITY = {
    "curtail": 0,
    "backup_activation": 1,
    "spinning_reserve": 2,
    "storage_charge": 3,
    "grid_absorption_check": 4,
}


def _window_label(alert: dict) -> str:
    start = datetime.fromisoformat(alert["start"])
    end = datetime.fromisoformat(alert["end"])
    if start.date() == end.date():
        return f"{start:%H:%M}-{end:%H:%M} UTC on {start:%d %b}"
    return f"{start:%d %b %H:%M} to {end:%d %b %H:%M} UTC"


def _mw(kw: float) -> str:
    return f"{kw / 1000:,.1f} MW"


def _mwh(kwh: float) -> str:
    return f"{kwh / 1000:,.1f} MWh"


def build_recommendations(site, alerts: list[dict]) -> list[dict]:
    """One or more recommended actions per flagged window."""
    recommendations: list[dict] = []
    # Track the battery through the horizon: charging it at noon means it can't
    # absorb the next surplus three hours later.
    projected_soc_kwh = float(site.storage_soc_kwh)

    for alert in sorted(alerts, key=lambda a: a["start"]):
        if alert["type"] == "over_generation":
            new_recs, projected_soc_kwh = _handle_over_generation(site, alert, projected_soc_kwh)
            recommendations += new_recs
        elif alert["type"] == "under_generation":
            new_recs, projected_soc_kwh = _handle_under_generation(site, alert, projected_soc_kwh)
            recommendations += new_recs
        elif alert["type"] == "ramp_down":
            recommendations.append(_handle_ramp_down(site, alert))
        elif alert["type"] == "ramp_up":
            recommendations.append(_handle_ramp_up(site, alert))

    recommendations.sort(
        key=lambda r: (ACTION_PRIORITY.get(r["action"], 9), r["window_start"])
    )
    return recommendations


def _handle_over_generation(site, alert, projected_soc_kwh: float):
    """Surplus energy has exactly three destinations: the battery, the grid, or the ground."""
    surplus_kwh = alert["surplus_kwh"]
    peak_surplus_kw = alert["peak_surplus_kw"]
    reference_kw = alert["reference_kw"]
    constrained = alert["reference_label"] == "export_limit"

    # If the site isn't export-constrained, the "surplus" is headroom against the
    # over-generation trigger rather than energy that physically can't leave.
    if surplus_kwh <= 0:
        surplus_kwh = max(alert["peak_kw"] - alert["threshold_kw"], 0.0) * alert["duration_hours"]
        peak_surplus_kw = max(alert["peak_kw"] - alert["threshold_kw"], 0.0)

    headroom_kwh = max(site.storage_capacity_kwh - projected_soc_kwh, 0.0)
    absorbable_kwh = min(surplus_kwh * STORAGE_CHARGE_EFFICIENCY, headroom_kwh)
    uncovered_kwh = max(surplus_kwh - absorbable_kwh / STORAGE_CHARGE_EFFICIENCY, 0.0)

    # Two different limits can bind. If the forecast clears the hard export
    # limit, that's the one you curtail back to; if it only clears the
    # over-generation trigger, the trigger is what you're managing against.
    # Getting this wrong produces advice like "curtail to nameplate", which
    # isn't a curtailment at all.
    breaches_hard_limit = alert["peak_kw"] > reference_kw
    cap_kw = reference_kw if breaches_hard_limit else alert["threshold_kw"]
    trim_kw = max(alert["peak_kw"] - cap_kw, 0.0)

    trigger_phrase = (
        f"past the {site.over_threshold:.0%} over-generation trigger "
        f"({_mw(alert['threshold_kw'])})"
    )
    if constrained:
        # Quote everything against the connection, since that's the limit the
        # operator is managing -- "49% of nameplate" is true but useless when
        # the substation is the thing about to be overloaded.
        breach_phrase = (
            f"{alert['peak_kw'] / reference_kw * 100:.0f}% of the "
            f"{_mw(reference_kw)} substation export limit"
        )
        if not breaches_hard_limit:
            breach_phrase += f" and {trigger_phrase}"
        spill_phrase = "with nowhere to go" if breaches_hard_limit else "above the trigger"
    else:
        breach_phrase = (
            f"{alert['peak_kw'] / site.capacity_kw * 100:.0f}% of "
            f"{_mw(site.capacity_kw)} nameplate and {trigger_phrase}"
        )
        spill_phrase = "above the trigger"
    limit_phrase = (
        f"the {_mw(reference_kw)} substation export limit"
        if constrained and breaches_hard_limit
        else trigger_phrase.replace("past ", "")
    )

    recommendations = []

    if absorbable_kwh > 0:
        projected_soc_kwh += absorbable_kwh
        soc_pct = projected_soc_kwh / site.storage_capacity_kwh * 100
        recommendations.append(
            {
                "id": f"{alert['id']}-storage",
                "site_id": site.id,
                "alert_id": alert["id"],
                "action": "storage_charge",
                "title": f"Charge storage with {_mwh(absorbable_kwh)}",
                "severity": "info" if uncovered_kwh <= 0 else alert["severity"],
                "window_start": alert["start"],
                "window_end": alert["end"],
                "quantity_kwh": round(absorbable_kwh, 1),
                "quantity": round(absorbable_kwh, 1),
                "quantity_unit": "kWh",
                "quantity_label": "Energy to store",
                "reason": (
                    f"Forecast reaches {_mw(alert['peak_kw'])} over {_window_label(alert)}, "
                    f"{_mwh(surplus_kwh)} past {limit_phrase}. The battery is at "
                    f"{site.storage_soc_kwh / max(site.storage_capacity_kwh, 1) * 100:.0f}% "
                    f"state of charge with {_mwh(headroom_kwh)} of headroom, so schedule a "
                    f"charge of {_mwh(absorbable_kwh)} instead of spilling it - that takes "
                    f"the pack to roughly {soc_pct:.0f}%."
                ),
            }
        )

    if uncovered_kwh > 0:
        if site.storage_capacity_kwh <= 0:
            storage_phrase = "There is no storage on site"
        elif headroom_kwh <= 0:
            storage_phrase = (
                f"The {site.storage_capacity_kwh / 1000:,.0f} MWh battery is already at "
                f"{projected_soc_kwh / site.storage_capacity_kwh * 100:.0f}% and has no headroom left"
            )
        else:
            storage_phrase = (
                f"Storage absorbs {_mwh(absorbable_kwh)} of it but cannot take the rest"
            )

        recommendations.append(
            {
                "id": f"{alert['id']}-curtail",
                "site_id": site.id,
                "alert_id": alert["id"],
                "action": "curtail",
                "title": f"Curtail {_mw(trim_kw)} at peak",
                "severity": alert["severity"],
                "window_start": alert["start"],
                "window_end": alert["end"],
                "quantity_kwh": round(uncovered_kwh, 1),
                "quantity": round(uncovered_kwh, 1),
                "quantity_unit": "kWh",
                "quantity_label": "Energy to curtail",
                "reason": (
                    f"Forecast peaks at {_mw(alert['peak_kw'])} across "
                    f"{alert['duration_hours']}h ({_window_label(alert)}), "
                    f"{breach_phrase}. "
                    f"{storage_phrase}, leaving {_mwh(uncovered_kwh)} {spill_phrase} - "
                    f"issue a curtailment instruction capped at {_mw(cap_kw)} export, "
                    f"trimming up to {_mw(trim_kw)} at the peak hour."
                ),
            }
        )

    return recommendations, projected_soc_kwh


def _handle_under_generation(site, alert, projected_soc_kwh: float):
    """Cover the gap from the battery first, then from somewhere that costs money."""
    shortfall_kwh = alert["shortfall_kwh"]
    peak_shortfall_kw = alert["peak_shortfall_kw"]
    # Don't drain the pack below 10%: batteries need a reserve, and a control
    # room that plans to hit 0% has no answer for the next surprise.
    usable_kwh = max(projected_soc_kwh - 0.10 * site.storage_capacity_kwh, 0.0)
    from_storage_kwh = min(shortfall_kwh, usable_kwh)
    remaining_kwh = max(shortfall_kwh - from_storage_kwh, 0.0)

    binding = alert["reference_label"]
    owed_phrase = (
        f"its {_mw(site.firm_commitment_kw)} firm delivery schedule"
        if binding == "delivery schedule"
        else f"the {site.under_threshold:.0%}-of-capacity floor ({_mw(alert['threshold_kw'])})"
    )

    recommendations = []
    if from_storage_kwh > 0:
        projected_soc_kwh -= from_storage_kwh
        recommendations.append(
            {
                "id": f"{alert['id']}-dispatch",
                "site_id": site.id,
                "alert_id": alert["id"],
                "action": "storage_charge",
                "title": f"Dispatch {_mwh(from_storage_kwh)} from storage",
                "severity": "info",
                "window_start": alert["start"],
                "window_end": alert["end"],
                "quantity_kwh": round(from_storage_kwh, 1),
                "quantity": round(from_storage_kwh, 1),
                "quantity_unit": "kWh",
                "quantity_label": "Energy to dispatch",
                "reason": (
                    f"Output drops to {_mw(alert['trough_kw'])} over {_window_label(alert)}, "
                    f"{_mwh(shortfall_kwh)} short of {owed_phrase}. The battery holds "
                    f"{_mwh(usable_kwh)} above its 10% reserve floor - discharge "
                    f"{_mwh(from_storage_kwh)} of it across the window before buying anything."
                ),
            }
        )

    if remaining_kwh > 0:
        covered = (
            f"after {_mwh(from_storage_kwh)} from storage, " if from_storage_kwh > 0 else ""
        )
        recommendations.append(
            {
                "id": f"{alert['id']}-backup",
                "site_id": site.id,
                "alert_id": alert["id"],
                "action": "backup_activation",
                "title": f"Secure {_mw(peak_shortfall_kw)} of replacement supply",
                "severity": alert["severity"],
                "window_start": alert["start"],
                "window_end": alert["end"],
                "quantity_kwh": round(remaining_kwh, 1),
                "quantity": round(remaining_kwh, 1),
                "quantity_unit": "kWh",
                "quantity_label": "Energy to cover",
                "reason": (
                    f"Forecast bottoms out at {_mw(alert['trough_kw'])} across "
                    f"{alert['duration_hours']}h ({_window_label(alert)}) against "
                    f"{owed_phrase} - a {_mw(peak_shortfall_kw)} gap at its worst. "
                    f"{covered.capitalize() if covered else ''}"
                    f"{_mwh(remaining_kwh)} still needs covering: schedule backup capacity "
                    f"or buy the block on the day-ahead market before gate closure."
                ),
            }
        )

    return recommendations, projected_soc_kwh


def _handle_ramp_down(site, alert) -> dict:
    return {
        "id": f"{alert['id']}-reserve",
        "site_id": site.id,
        "alert_id": alert["id"],
        "action": "spinning_reserve",
        "title": f"Hold {_mw(abs(alert['delta_kw']))} of spinning reserve",
        "severity": alert["severity"],
        "window_start": alert["start"],
        "window_end": alert["end"],
        "quantity_kwh": 0.0,
        "quantity": round(abs(alert["delta_kw"]), 1),
        "quantity_unit": "kW",
        "quantity_label": "Reserve to hold",
        "reason": (
            f"Output falls {_mw(abs(alert['delta_kw']))} between "
            f"{_window_label(alert)} - up to "
            f"{alert['pct_of_capacity_per_hour']:.0f}% of capacity in a single hour, past this "
            f"site's {site.ramp_threshold:.0%} ramp trigger. Have reserve synchronised and "
            f"ready to pick up {_mw(abs(alert['delta_kw']))} before the ramp starts, not after."
        ),
    }


def _handle_ramp_up(site, alert) -> dict:
    return {
        "id": f"{alert['id']}-absorption",
        "site_id": site.id,
        "alert_id": alert["id"],
        "action": "grid_absorption_check",
        "title": f"Confirm {_mw(abs(alert['delta_kw']))} of absorption capacity",
        "severity": alert["severity"],
        "window_start": alert["start"],
        "window_end": alert["end"],
        "quantity_kwh": 0.0,
        "quantity": round(abs(alert["delta_kw"]), 1),
        "quantity_unit": "kW",
        "quantity_label": "Absorption needed",
        "reason": (
            f"Output climbs {_mw(abs(alert['delta_kw']))} between {_window_label(alert)} "
            f"to {_mw(alert['to_kw'])}, peaking at "
            f"{alert['pct_of_capacity_per_hour']:.0f}% of capacity in one hour. "
            f"Check downstream absorption and back off conventional units in advance, "
            f"or this arrives as an unplanned surplus."
        ),
    }
