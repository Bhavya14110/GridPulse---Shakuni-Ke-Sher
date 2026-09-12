# GridPulse — architecture

This document covers how the system fits together and, more importantly, *why*
each piece works the way it does. The README covers setup and results.

---

## 1. The shape of the problem

A grid operator's question is not "how much will this farm produce". It is:

> Over the next three days, is any of my generation going to do something I need
> to act on before it happens — and what is the action?

That decomposes into three distinct problems with three distinct right answers:

| Problem | Right tool | Why |
|---|---|---|
| Predicting output | Machine learning | The weather→power relationship is non-linear, interacts across variables, and is exactly what gradient boosting is good at. |
| Deciding what's a problem | Rules | Thresholds are contractual and physical. An operator must be able to see and change them. |
| Deciding what to do | Rules + arithmetic | The action has to be defensible line by line to whoever signs off on curtailing 100 MW. |

GridPulse uses ML for the first and deterministic logic for the other two. That
split is deliberate, not a shortcut: a learned recommendation engine would be
both less accurate here and impossible to justify in a control room.

---

## 2. Data flow

```
┌──────────────────────────────────────────────────────────────────────┐
│ OPEN-METEO                                                           │
│   /v1/forecast   past_days=2, forecast_days=4  → live NWP output     │
│   /v1/archive    15 months of ERA5 reanalysis  → training weather    │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
         ┌──────────────────────┴────────────────────┐
         │ OFFLINE (run once)          ONLINE (per request/refresh)
         ▼                                           ▼
┌─────────────────────────┐            ┌──────────────────────────────┐
│ build_historical_       │            │ weather_service              │
│ dataset.py              │            │   in-process TTL cache       │
│   ERA5 → physics model  │            └───────────────┬──────────────┘
│   → 65,808 site-hours   │                            │
└────────────┬────────────┘                            ▼
             ▼                             ┌──────────────────────────┐
┌─────────────────────────┐                │ feature_builder          │
│ train_model.py          │                │   same code path as      │
│   chronological split   │                │   training — no skew     │
│   XGBoost per tech      │                └───────────┬──────────────┘
│   → *_model.json        │                            ▼
│   → metrics.json        │───── loaded ──────▶ ┌──────────────────────┐
└─────────────────────────┘                     │ forecasting_service  │
                                                │   recursive walk     │
                                                │   confidence bands   │
                                                │   physical clamp     │
                                                └───────────┬──────────┘
                                                            ▼
                                   ┌────────────────────────────────────┐
                                   │ alert_engine → recommendation_engine│
                                   └────────────────────┬───────────────┘
                                                        ▼
                                   ┌────────────────────────────────────┐
                                   │ forecast_store (SQLite cache, 20m) │
                                   │   ← APScheduler refresh every 15m  │
                                   └────────────────────┬───────────────┘
                                                        ▼
                                              FastAPI  →  Next.js
```

---

## 3. Design decisions

### 3.1 The model predicts capacity factor, not kilowatts

Target is `generation / nameplate`, in [0, 1].

Three consequences, all good:

- **One model serves every site of that technology.** A 92 MW farm and a 240 MW
  array have the same physics; only the scalar differs.
- **The error metric is directly interpretable.** MAE in capacity-factor points
  *is* MAE as a percentage of capacity, which is how the industry quotes
  forecast accuracy.
- **New sites need no retraining.** Add a site through the API and it forecasts
  on the next refresh. This is the single biggest practical win of the choice.

Nameplate is still passed as a feature, so the model can learn any size-related
effects that do exist.

### 3.2 Inference is recursive

The feature set includes lagged generation (1h, 3h, 24h rolling mean), which is
real signal — especially for wind, where the previous hour is genuinely
informative about the next.

But we don't know next Tuesday's generation. So `_predict_recursive` walks the
horizon hour by hour and feeds each prediction back in as the next hour's lag.
That's what operational forecasters do. The alternative — dropping lag features
— throws away signal the model demonstrably uses (`lag_cf_1h` is the second most
important feature for wind).

The horizon is warm-started from the past 48 hours, which we get free: the same
Open-Meteo call requests `past_days=2` alongside the forecast days.

### 3.3 Train/serve skew is structurally prevented

`feature_builder.build_features` is the *only* place features are constructed.
Training calls it; inference calls it. There is no second implementation to
drift out of sync, which is the most common way an ML demo silently breaks.

`FEATURE_COLUMNS` fixes the column order, because XGBoost consumes a positional
matrix.

### 3.4 Confidence bands come from held-out residuals

Not from a hand-picked percentage. Training measures the residual spread on the
chronological holdout, bucketed by predicted capacity factor, and writes those
buckets to `metrics.json`. At inference we look up the bucket for each hour.

Bucketing matters: a model predicting near zero or near rated output is far more
certain than one predicting the middle of a ramp, and a flat ± band hides that.
The band is then widened with lead time (1.8% per hour, capped at 2.4×), because
a 70-hour-ahead forecast is a different animal from a 1-hour-ahead one.

Bands are quoted as p10–p90 (±1.28σ) — the interval energy forecasting normally
uses.

### 3.5 Predictions are clamped to physical zero

Trees extrapolate sloppily near zero and will happily emit a few hundred kW of
solar at 2am. Physics says otherwise: no sun above the horizon, or wind below
cut-in, means exactly zero.

So `_potential_kw` computes the clear-sky ceiling (for solar) or the physics
curve on forecast wind (for wind), and any hour where that is zero has its
prediction and its band forced to zero. Real forecasters apply the same clamp;
without it the chart carries a visible fake baseline through every night.

### 3.6 Solar geometry is computed, not fetched

`solar_position` implements NOAA's low-precision solar position algorithm —
about 30 lines, no dependency, no API call. It gives us:

- **Sun elevation**, a strong feature: it tells the model *why* irradiance is
  low (dusk vs. cloud), which the irradiance value alone cannot.
- **Clear-sky GHI** (Haurwitz model), which gives a **clear-sky index** —
  essentially "how cloudy is it, really" — and defines each solar site's
  productive window without hardcoding "9am to 4pm" anywhere.

### 3.7 The backtest never peeks

The "yesterday's forecast vs actual" panel is the credibility feature, so it has
to be built honestly.

`rolling_backtest` does a rolling-origin evaluation: for each of the last N
days, it rewinds to that morning, warm-starts the model on data up to that point
only, and runs 24 hours forward with no further ground truth. The results are
stitched together and scored.

Letting the model use the real lagged actuals for the hours it's "predicting"
would make the chart look superb and mean nothing — it would be measuring
one-hour-ahead performance and labelling it day-ahead.

### 3.8 Alerts compare against site-specific references

The three rules are the ones in the problem statement, but the number each one
compares against is per-site, because that's what makes the output actionable:

| Rule | Reference | Rationale |
|---|---|---|
| Over-generation | 85% of **grid export limit** | A 180 MW plant behind a 95 MW substation over-generates at 81 MW. Connection constraints cause most real curtailment. |
| Under-generation | max(15% of capacity, **firm delivery schedule**) | A plant that sold 45 MW day-ahead is short at 30 MW. That's the exposure. |
| Ramp | 25% of capacity per hour | Ramp rate is about reserve, which scales with the asset. |

Sites with neither constraint set fall back to plain percentage-of-capacity, so
the default behaviour is exactly the spec.

Two further refinements stop the alert list becoming noise:

- **Minimum duration.** A one-hour dip doesn't need a backup plant spun up.
  Sustained events (≥2h) do.
- **Productive-window gating.** For a solar site without a delivery schedule,
  low output is only flagged when clear-sky potential says it *should* have been
  producing (≥40% of capacity). Otherwise every dusk would be an alert.
- **Ramp merging.** Consecutive same-direction ramp hours are one event. A front
  crossing a wind farm over four hours is one thing to schedule against, not
  three alerts burying everything else.

Severity scales with both magnitude *and* duration — four hours of mild
shortfall is still four hours of replacement power to find.

### 3.9 Recommendations track state forward

The recommendation engine walks alerts in chronological order carrying a
projected battery state of charge. Charging at noon genuinely reduces what's
available for the surplus three hours later, and discharging in the morning
frees headroom for the afternoon. Without that, every recommendation would
assume a fresh battery and the advice would be wrong by lunchtime.

It also applies round-trip efficiency (92%) and refuses to plan below a 10%
reserve floor — a control room that plans to hit 0% has no answer for the next
surprise.

When storage covers only part of a surplus, it emits **both** actions: charge
what fits, curtail the rest. That's the real answer.

### 3.10 One cached payload feeds everything

`forecast_store` computes a site's forecast, alerts and recommendations
together, stores the bundle as JSON in SQLite, and serves every endpoint from
it. Two reasons:

- **Speed.** Building a payload means an Open-Meteo round trip plus ~150
  sequential model calls — several seconds. Cached responses return in ~5 ms. A
  demo that stalls on every click reads as broken.
- **Consistency.** The forecast endpoint, the alerts endpoint, the
  recommendations endpoint and the portfolio summary are all derived from the
  same snapshot, so they can never disagree with each other.

A per-site lock prevents a cold cache from triggering six identical concurrent
rebuilds. The APScheduler job fires once ~2 seconds after startup so the cache
is warm before anyone opens the browser.

---

## 4. What would change for production

Being clear about the gap is part of the design.

| Now | Production |
|---|---|
| Physics-derived training targets | Real SCADA history — a file swap in `train_model.py` |
| Point forecast + residual bands | Quantile regression (`reg:quantileerror`) for calibrated p10/p50/p90 |
| Single NWP source | Multi-model ensemble (ECMWF + GFS + ICON); spread across models is itself an uncertainty signal |
| SQLite | Postgres + TimescaleDB for real hourly history at fleet scale |
| Recommendations as advice | Write into the dispatch/SCADA system with an approval step |
| Thresholds per site | Thresholds per site *per season*, and price-aware — curtailment economics depend on whether prices are negative |
| Retrain manually | Scheduled retraining with drift monitoring on rolling MAE |

The pipeline shape wouldn't change. Each row above is a swap behind an interface
that already exists.

---

## 5. Repository map

Annotated layout is in the README. The files worth reading first, in order:

1. `backend/app/services/generation_model.py` — the physics everything rests on
2. `backend/ml/build_historical_dataset.py` — how the training data is made
3. `backend/ml/train_model.py` — the split, the metrics, the baselines
4. `backend/app/services/forecasting_service.py` — recursive inference, bands, backtest
5. `backend/app/services/alert_engine.py` — the three rules and their references
6. `backend/app/services/recommendation_engine.py` — actions and reason strings
